"""API request-limit security boundaries."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from werewolf_agent.api.middleware.limits import (
    PrincipalRateLimiter,
    RateLimitBuckets,
    RequestLimitsMiddleware,
)


def _client(*, request_limit: int = 2) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        RequestLimitsMiddleware,
        max_body_bytes=1024,
        timeout_seconds=1,
        rate_limit_requests=request_limit,
        rate_limit_window_seconds=60,
        max_concurrent_requests=4,
    )

    @app.get("/api/v1/games/{game_id}")
    def game(game_id: str) -> dict[str, str]:
        return {"game_id": game_id}

    return TestClient(app)


def test_changing_bearer_token_cannot_bypass_the_ip_limit() -> None:
    client = _client()

    first = client.get("/api/v1/games/game-1", headers={"Authorization": "Bearer token-a"})
    second = client.get("/api/v1/games/game-1", headers={"Authorization": "Bearer token-a"})
    bypass = client.get("/api/v1/games/game-1", headers={"Authorization": "Bearer token-b"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert bypass.status_code == 429
    assert bypass.json()["code"] == "request.rate_limited"


def test_one_network_cannot_bypass_its_limit_by_changing_game_id() -> None:
    client = _client()
    headers = {"Authorization": "Bearer stable-token"}

    first = client.get("/api/v1/games/game-1", headers=headers)
    second = client.get("/api/v1/games/game-2", headers=headers)
    bypass = client.get("/api/v1/games/game-3", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert bypass.status_code == 429


def test_unauthenticated_requests_are_still_limited_by_ip() -> None:
    client = _client(request_limit=1)

    first = client.get("/api/v1/games/game-1")
    second = client.get("/api/v1/games/game-2")

    assert first.status_code == 200
    assert second.status_code == 429


def test_verified_principal_is_limited_across_networks_and_token_refreshes() -> None:
    limiter = PrincipalRateLimiter(request_limit=2, window_seconds=60, max_buckets=10)

    assert limiter.allow(user_id="verified-user-1", path="/api/v1/games/game-1")
    assert limiter.allow(user_id="verified-user-1", path="/api/v1/games/game-2")
    assert not limiter.allow(user_id="verified-user-1", path="/api/v1/games/game-3")


def test_rate_limit_bucket_storage_is_bounded() -> None:
    buckets = RateLimitBuckets(request_limit=10, window_seconds=60, max_buckets=3)
    for index in range(3):
        assert buckets.allow((f"ip:198.51.100.{index}",))
    for index in range(3, 10):
        assert not buckets.allow((f"ip:198.51.100.{index}",))

    assert len(buckets._requests) == 3
    assert len(buckets._last_seen) == 3


def test_concurrent_requests_cannot_exceed_the_configured_limit() -> None:
    request_limit = 20
    buckets = RateLimitBuckets(
        request_limit=request_limit,
        window_seconds=60,
        max_buckets=10,
    )

    with ThreadPoolExecutor(max_workers=32) as executor:
        allowed = list(executor.map(lambda _: buckets.allow(("principal:user-1",)), range(200)))

    assert sum(allowed) == request_limit


def test_request_body_read_is_covered_by_timeout() -> None:
    app_called = False
    sent: list[dict[str, Any]] = []

    async def app(_scope: object, _receive: object, _send: object) -> None:
        nonlocal app_called
        app_called = True

    middleware = RequestLimitsMiddleware(
        app,
        max_body_bytes=1024,
        timeout_seconds=0.01,
        rate_limit_requests=10,
        rate_limit_window_seconds=60,
        max_concurrent_requests=1,
    )
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/games",
        "raw_path": b"/api/v1/games",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("198.51.100.1", 1234),
        "server": ("testserver", 80),
    }

    async def slow_receive() -> dict[str, Any]:
        await asyncio.sleep(1)
        return {"type": "http.request", "body": b"{}", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    asyncio.run(middleware(scope, slow_receive, send))  # type: ignore[arg-type]

    assert app_called is False
    assert sent[0]["status"] == 504


def test_timeout_does_not_send_a_second_response_after_response_started() -> None:
    sent: list[dict[str, Any]] = []

    async def app(_scope: object, _receive: object, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}", "more_body": False})
        await asyncio.sleep(1)

    middleware = RequestLimitsMiddleware(
        app,
        max_body_bytes=1024,
        timeout_seconds=0.01,
        rate_limit_requests=10,
        rate_limit_window_seconds=60,
        max_concurrent_requests=1,
    )
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/operations/operation-1",
        "raw_path": b"/api/v1/operations/operation-1",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("198.51.100.1", 1234),
        "server": ("testserver", 80),
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))  # type: ignore[arg-type]

    assert [message["type"] for message in sent] == [
        "http.response.start",
        "http.response.body",
    ]
