"""Bound request size, duration, and request rate."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from threading import Lock
from typing import Any

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

RequestHandler = Callable[[Request], Awaitable[Response]]


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


class RequestLimitsMiddleware(BaseHTTPMiddleware):
    """Apply bounded body, timeout, and in-process burst protection."""

    def __init__(
        self,
        app: Any,
        *,
        max_body_bytes: int,
        timeout_seconds: float,
        rate_limit_requests: int,
        rate_limit_window_seconds: int,
        max_concurrent_requests: int,
    ) -> None:
        """Create middleware from validated runtime settings."""
        super().__init__(app)
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

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        """Reject oversized, excessive, or timed-out requests."""
        content_length = request.headers.get("content-length")
        parsed_content_length = _content_length(content_length)
        if parsed_content_length is None:
            return _problem(
                400,
                "request.invalid_content_length",
                "送信内容の長さを確認できません。",
                request,
            )
        if parsed_content_length > self._max_body_bytes:
            return _problem(
                413,
                "request.body_too_large",
                "送信内容が大きすぎます。",
                request,
            )
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await _bounded_body(request, self._max_body_bytes)
            if body is None:
                return _problem(
                    413,
                    "request.body_too_large",
                    "送信内容が大きすぎます。",
                    request,
                )
        if not self._buckets.allow(_network_rate_keys(request)):
            return _problem(
                429,
                "request.rate_limited",
                "しばらく待ってからもう一度お試しください。",
                request,
            )
        if not await self._enter_request():
            return _problem(
                503,
                "request.concurrency_limited",
                "現在アクセスが集中しています。しばらく待ってからお試しください。",
                request,
            )
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await call_next(request)
        except TimeoutError:
            return _problem(
                504,
                "request.timed_out",
                "処理が時間内に完了しませんでした。",
                request,
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


async def _bounded_body(request: Request, limit: int) -> bytes | None:
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            return None
        chunks.append(chunk)
    body = b"".join(chunks)
    request._body = body  # Starlette replays the validated body to downstream handlers.
    return body


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


def _problem(status: int, code: str, detail: str, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": f"urn:werewolf-agent:error:{code}",
            "title": detail,
            "status": status,
            "detail": detail,
            "instance": request.url.path,
            "code": code,
        },
    )


__all__ = ["PrincipalRateLimiter", "RateLimitBuckets", "RequestLimitsMiddleware"]
