"""Browser検査が使用するHTTP API操作。"""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import httpx


def response_json(response: httpx.Response) -> dict[str, Any]:
    """成功応答をJSON objectとして返す。"""
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError("API response must be an object")
    return payload


def create_authenticated_user(
    client: httpx.Client,
    supabase_url: str,
    publishable_key: str,
) -> tuple[str, str, str]:
    """品質run専用の認証利用者を作成する。"""
    email = f"streamlit-e2e-{uuid4()}@example.com"
    password = f"Streamlit-{uuid4()}!"
    payload = response_json(
        client.post(
            f"{supabase_url.rstrip('/')}/auth/v1/signup",
            json={"email": email, "password": password},
            headers={"apikey": publishable_key},
        )
    )
    return email, password, str(payload["access_token"])


def wait_for_operation(
    client: httpx.Client,
    api_url: str,
    token: str,
    operation: dict[str, Any],
    *,
    timeout_seconds: float = 30,
) -> dict[str, Any]:
    """非同期operationが確定するまで待つ。"""
    deadline = time.monotonic() + timeout_seconds
    current = operation
    while current.get("status") in {"queued", "running"}:
        if time.monotonic() >= deadline:
            raise TimeoutError("operation timed out")
        time.sleep(0.25)
        current = response_json(
            client.get(
                f"{api_url.rstrip('/')}/api/v1/operations/{current['operation_id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
        )
    if current.get("status") == "failed":
        error = current.get("error")
        detail = error.get("detail") if isinstance(error, dict) else None
        raise RuntimeError(str(detail or "operation failed"))
    return current


def post_operation(
    client: httpx.Client,
    api_url: str,
    path: str,
    token: str,
    body: dict[str, Any],
    *,
    timeout_seconds: float = 30,
) -> dict[str, Any]:
    """冪等key付きcommandを送信して完了結果を返す。"""
    operation = response_json(
        client.post(
            f"{api_url.rstrip('/')}{path}",
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": str(uuid4()),
            },
        )
    )
    return wait_for_operation(
        client,
        api_url,
        token,
        operation,
        timeout_seconds=timeout_seconds,
    )


def create_completed_game(client: httpx.Client, api_url: str, token: str) -> str:
    """Fake LLMで完了済みgameを一件作成する。"""
    created = post_operation(
        client,
        api_url,
        "/api/v1/games",
        token,
        {
            "manual_player_id": None,
            "seed": 7,
            "setup": {"mode": "template", "template_id": "standard_6"},
        },
    )
    result = created.get("result")
    if not isinstance(result, dict) or not result.get("game_id"):
        raise RuntimeError("game creation did not return game_id")
    game_id = str(result["game_id"])
    headers = {"Authorization": f"Bearer {token}"}
    game = response_json(client.get(f"{api_url}/api/v1/games/{game_id}", headers=headers))
    for _ in range(64):
        state = game.get("state")
        if not isinstance(state, dict):
            raise RuntimeError("game state is missing")
        if state.get("status") == "completed":
            return game_id
        post_operation(
            client,
            api_url,
            f"/api/v1/games/{game_id}/advance",
            token,
            {"expected_version": state["version"]},
        )
        game = response_json(client.get(f"{api_url}/api/v1/games/{game_id}", headers=headers))
    raise RuntimeError("game did not complete within 64 steps")


__all__ = [
    "create_authenticated_user",
    "create_completed_game",
    "post_operation",
    "response_json",
    "wait_for_operation",
]
