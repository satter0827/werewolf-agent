"""明示実行するLocal LLM Streamlit画面確認。"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page, expect

from scripts.browser.scenarios.api import post_operation, response_json


def test_streamlit_displays_one_local_llm_game(
    page: Page,
    api_client: httpx.Client,
    streamlit_url: str,
    screenshot_directory: Path,
    capture_public_screenshot: Callable[[Page, str], Path],
    device_name: str,
) -> None:
    if device_name != "desktop":
        pytest.skip("Local LLM review uses one desktop game")
    if os.environ.get("PLAYWRIGHT_LOCAL_LLM") != "1":
        pytest.skip("Explicit Local LLM review only")

    api_url = os.environ.get("PLAYWRIGHT_API_URL", "http://api:8000")
    email = os.environ["PLAYWRIGHT_LOCAL_EMAIL"]
    password = os.environ["PLAYWRIGHT_LOCAL_PASSWORD"]
    supabase_url = os.environ["PLAYWRIGHT_SUPABASE_URL"]
    supabase_key = os.environ["PLAYWRIGHT_SUPABASE_PUBLISHABLE_KEY"]
    network_events: list[dict[str, object]] = []

    auth_url = f"{supabase_url}/auth/v1/token?grant_type=password"
    auth_response = api_client.post(
        auth_url,
        json={"email": email, "password": password},
        headers={"apikey": supabase_key},
    )
    network_events.append({"method": "POST", "status": auth_response.status_code, "url": auth_url})
    token = str(response_json(auth_response)["access_token"])

    created = post_operation(
        api_client,
        api_url,
        "/api/v1/games",
        token,
        {
            "manual_player_id": None,
            "narration_mode": "standard",
            "seed": 7,
            "setup": {"mode": "template", "template_id": "standard_6"},
        },
        timeout_seconds=1_200,
    )
    result = created.get("result")
    assert isinstance(result, dict) and result.get("game_id")
    game_id = str(result["game_id"])

    _open_streamlit_record(page, streamlit_url, email, password)
    capture_public_screenshot(page, "streamlit-created.png")

    headers = {"Authorization": f"Bearer {token}"}
    game_url = f"{api_url}/api/v1/games/{game_id}"
    game = response_json(api_client.get(game_url, headers=headers))
    for step in range(64):
        state = game.get("state")
        assert isinstance(state, dict)
        if state.get("status") == "completed":
            break
        post_operation(
            api_client,
            api_url,
            f"/api/v1/games/{game_id}/advance",
            token,
            {"expected_version": state["version"]},
            timeout_seconds=1_200,
        )
        game_response = api_client.get(game_url, headers=headers)
        network_events.append(
            {"method": "GET", "status": game_response.status_code, "url": game_url}
        )
        game = response_json(game_response)
        if step == 0:
            _capture_record(
                page,
                streamlit_url,
                email,
                password,
                capture_public_screenshot,
                "streamlit-progress.png",
            )
    state = game.get("state")
    assert isinstance(state, dict) and state.get("status") == "completed"
    _capture_record(
        page,
        streamlit_url,
        email,
        password,
        capture_public_screenshot,
        "streamlit-finished.png",
        required_text="結果サマリー",
    )
    _capture_login_error(
        page,
        streamlit_url,
        email,
        capture_public_screenshot,
        "streamlit-error.png",
    )

    timeline_url = f"{api_url}/api/v1/games/{game_id}/timeline?after=0&limit=100"
    timeline_response = api_client.get(timeline_url, headers=headers)
    network_events.append(
        {"method": "GET", "status": timeline_response.status_code, "url": timeline_url}
    )
    timeline = response_json(timeline_response)
    items = timeline.get("items")
    assert isinstance(items, list) and items
    assert not any(":1234/" in str(event["url"]) for event in network_events)

    evidence_root = screenshot_directory.parent
    _write_json(evidence_root / "network.json", network_events)
    _write_json(evidence_root / "console.json", [])
    _write_json(
        evidence_root / "local-ui-result.json",
        {
            "game_id": game_id,
            "api_status": state["status"],
            "dom_status": "completed",
            "api_state": game,
            "api_timeline": timeline,
        },
    )


def _open_streamlit_record(page: Page, url: str, email: str, password: str) -> None:
    page.goto(url)
    page.get_by_text("ログイン", exact=True).first.click()
    page.get_by_label("メールアドレス").fill(email)
    page.get_by_label("パスワード").fill(password)
    page.get_by_role("button", name="ログイン", exact=True).last.click()
    expect(page.get_by_text(email)).to_be_visible(timeout=30_000)
    page.get_by_role("button", name="記録を開く", exact=True).click()
    expect(page.get_by_text("ゲーム卓", exact=True)).to_be_visible()
    expect(page.get_by_text("公開タイムライン", exact=True).first).to_be_visible()


def _capture_record(
    owner: Page,
    url: str,
    email: str,
    password: str,
    capture_public_screenshot: Callable[[Page, str], Path],
    filename: str,
    *,
    required_text: str | None = None,
) -> None:
    page = owner.context.new_page()
    try:
        _open_streamlit_record(page, url, email, password)
        if required_text:
            expect(page.get_by_text(required_text, exact=True)).to_be_visible(timeout=30_000)
        capture_public_screenshot(page, filename)
    finally:
        page.close()


def _capture_login_error(
    owner: Page,
    url: str,
    email: str,
    capture_public_screenshot: Callable[[Page, str], Path],
    filename: str,
) -> None:
    page = owner.context.new_page()
    try:
        page.goto(url)
        page.get_by_text("ログイン", exact=True).first.click()
        page.get_by_label("メールアドレス").fill(email)
        page.get_by_label("パスワード").fill("invalid-local-review-password")
        page.get_by_role("button", name="ログイン", exact=True).last.click()
        expect(page.locator('[data-testid="stAlert"]')).to_be_visible()
        capture_public_screenshot(page, filename)
    finally:
        page.close()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
