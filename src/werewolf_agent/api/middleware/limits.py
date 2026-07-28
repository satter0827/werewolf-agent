"""Bound request size, duration, and request rate."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from threading import Lock

from fastapi.responses import JSONResponse
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from werewolf_agent.contracts import ErrorCode, problem_details_from_spec

ReceiveFactory = Callable[[], Awaitable[Message]]


class _BodyTooLarge(Exception):
    """Stop request processing when streamed body bytes exceed the limit."""


class RateLimitBuckets:
    """Bounded sliding-window buckets shared by trusted rate-limit boundaries."""

    def __init__(self, *, request_limit: int, window_seconds: int, max_buckets: int) -> None:
        """Create bounded in-process request buckets."""
        self._request_limit = request_limit
        self._window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._last_seen: dict[str, float] = {}
        self._max_buckets = max_buckets
        self._lock = Lock()

    def allow(self, keys: tuple[str, ...]) -> bool:
        """Consume one request from every independent key when all have capacity."""
        with self._lock:
            return self._allow_locked(keys)

    def _allow_locked(self, keys: tuple[str, ...]) -> bool:
        """Update all related buckets atomically."""
        now = time.monotonic()
        cutoff = now - self._window_seconds
        unique_keys = tuple(dict.fromkeys(keys))
        self._remove_expired(unique_keys, cutoff)
        new_keys = [key for key in unique_keys if key not in self._requests]
        if len(self._requests) + len(new_keys) > self._max_buckets:
            self._remove_expired(tuple(self._requests), cutoff)
            new_keys = [key for key in unique_keys if key not in self._requests]
            if len(self._requests) + len(new_keys) > self._max_buckets:
                return False
        if any(len(self._requests.get(key, ())) >= self._request_limit for key in unique_keys):
            return False
        for key in unique_keys:
            self._requests[key].append(now)
            self._last_seen[key] = now
        return True

    def _remove_expired(self, keys: tuple[str, ...], cutoff: float) -> None:
        for key in keys:
            entries = self._requests.get(key)
            if entries is None:
                continue
            while entries and entries[0] <= cutoff:
                entries.popleft()
            if not entries:
                self._requests.pop(key, None)
                self._last_seen.pop(key, None)


class PrincipalRateLimiter:
    """Apply rate limits only to identities returned by verified authentication."""

    def __init__(self, *, request_limit: int, window_seconds: int, max_buckets: int) -> None:
        """Create verified-principal and principal-game buckets."""
        self._buckets = RateLimitBuckets(
            request_limit=request_limit,
            window_seconds=window_seconds,
            max_buckets=max_buckets,
        )

    def allow(self, *, user_id: str, path: str) -> bool:
        """Consume global user and per-game capacity for one verified principal."""
        game_scope = _game_scope(path)
        return self._buckets.allow(
            (
                f"principal:{user_id}",
                f"principal_game:{user_id}:{game_scope}",
            )
        )


class RequestLimitsMiddleware:
    """Apply bounded body, timeout, and in-process burst protection."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        timeout_seconds: float,
        rate_limit_requests: int,
        rate_limit_window_seconds: int,
        max_concurrent_requests: int,
    ) -> None:
        """Create middleware from validated runtime settings."""
        self.app = app
        self._max_body_bytes = max_body_bytes
        self._timeout_seconds = timeout_seconds
        self._buckets = RateLimitBuckets(
            request_limit=rate_limit_requests,
            window_seconds=rate_limit_window_seconds,
            max_buckets=max(1024, rate_limit_requests * max_concurrent_requests * 4),
        )
        self._max_concurrent_requests = max_concurrent_requests
        self._active_requests = 0
        self._active_requests_lock = asyncio.Lock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reject oversized, excessive, or timed-out HTTP requests."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        content_length = request.headers.get("content-length")
        parsed_content_length = _content_length(content_length)
        if parsed_content_length is None:
            await _problem(
                ErrorCode.REQUEST_INVALID_CONTENT_LENGTH,
                request,
                scope,
                receive,
                send,
            )
            return
        if parsed_content_length > self._max_body_bytes:
            await _problem(
                ErrorCode.REQUEST_BODY_TOO_LARGE,
                request,
                scope,
                receive,
                send,
            )
            return
        if not self._buckets.allow(_network_rate_keys(request)):
            await _problem(
                ErrorCode.REQUEST_RATE_LIMITED,
                request,
                scope,
                receive,
                send,
            )
            return
        if not await self._enter_request():
            await _problem(
                ErrorCode.REQUEST_CONCURRENCY_LIMITED,
                request,
                scope,
                receive,
                send,
            )
            return
        response_started = False

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            async with asyncio.timeout(self._timeout_seconds):
                bounded_receive = await _buffer_bounded_receive(
                    receive,
                    self._max_body_bytes,
                )
                await self.app(scope, bounded_receive, tracked_send)
        except _BodyTooLarge:
            await _problem(
                ErrorCode.REQUEST_BODY_TOO_LARGE,
                request,
                scope,
                receive,
                send,
            )
        except TimeoutError:
            if not response_started:
                await _problem(
                    ErrorCode.REQUEST_TIMED_OUT,
                    request,
                    scope,
                    receive,
                    send,
                )
        finally:
            await self._leave_request()

    async def _enter_request(self) -> bool:
        async with self._active_requests_lock:
            if self._active_requests >= self._max_concurrent_requests:
                return False
            self._active_requests += 1
            return True

    async def _leave_request(self) -> None:
        async with self._active_requests_lock:
            self._active_requests -= 1


def _content_length(value: str | None) -> int | None:
    if value is None:
        return 0
    try:
        length = int(value)
    except ValueError:
        return None
    return length if length >= 0 else None


async def _buffer_bounded_receive(receive: Receive, limit: int) -> ReceiveFactory:
    messages: deque[Message] = deque()
    size = 0
    while True:
        message = await receive()
        messages.append(message)
        if message["type"] == "http.disconnect":
            break
        if message["type"] != "http.request":
            continue
        size += len(message.get("body", b""))
        if size > limit:
            raise _BodyTooLarge
        if not message.get("more_body", False):
            break

    async def bounded() -> Message:
        if messages:
            return messages.popleft()
        return {"type": "http.disconnect"}

    return bounded


def _network_rate_keys(request: Request) -> tuple[str, ...]:
    host = request.client.host if request.client else "unknown"
    game_scope = _game_scope(request.url.path)
    return (f"ip:{host}", f"ip_game:{host}:{game_scope}")


def _game_scope(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    try:
        games_index = parts.index("games")
    except ValueError:
        return "global"
    if games_index + 1 >= len(parts):
        return "games"
    return parts[games_index + 1][:64]


async def _problem(
    code: ErrorCode,
    request: Request,
    scope: Scope,
    receive: Receive,
    send: Send,
) -> None:
    problem = problem_details_from_spec(code, instance=request.url.path)
    response = JSONResponse(
        status_code=problem.status,
        media_type="application/problem+json",
        content=problem.model_dump(mode="json"),
    )
    await response(scope, receive, send)


__all__ = ["PrincipalRateLimiter", "RateLimitBuckets", "RequestLimitsMiddleware"]
