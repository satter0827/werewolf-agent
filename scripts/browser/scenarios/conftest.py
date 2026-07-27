"""Python Playwright scenarioの共有fixture。"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import httpx
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, Route, expect

LOCAL_HOSTS = frozenset(
    {"127.0.0.1", "::1", "api", "host.docker.internal", "localhost", "streamlit"}
)
DEVICES = {
    "desktop": "Desktop Chrome",
    "mobile": "Pixel 7",
}


@pytest.fixture(params=tuple(DEVICES))
def device_name(request: pytest.FixtureRequest) -> str:
    """Desktopとmobileを同じscenarioへ適用する。"""
    return str(request.param)


@pytest.fixture
def browser_context_args(
    browser_context_args: dict[str, object],
    playwright: Playwright,
    device_name: str,
) -> dict[str, object]:
    """選択deviceのChromium context設定を返す。"""
    return {**browser_context_args, **playwright.devices[DEVICES[device_name]]}


@pytest.fixture
def context(
    browser: Browser,
    browser_context_args: dict[str, object],
    output_path: str,
) -> Iterator[BrowserContext]:
    """各scenarioを独立contextとtraceへ分離する。"""
    context = browser.new_context(**cast(Any, browser_context_args))
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    try:
        yield context
    finally:
        trace = Path(output_path) / "trace.zip"
        trace.parent.mkdir(parents=True, exist_ok=True)
        context.tracing.stop(path=trace)
        context.close()


@pytest.fixture
def page(context: BrowserContext) -> Iterator[Page]:
    """外部通信とconsole errorを拒否する検査pageを返す。"""
    expected_instance = os.environ.get("PLAYWRIGHT_EXPECTED_INSTANCE_ID", "")
    assert expected_instance, "E2E対象instance IDが設定されていません"
    api_url = os.environ.get("PLAYWRIGHT_API_URL", "http://api:8000")
    health = httpx.get(f"{api_url}/health", timeout=10)
    health.raise_for_status()
    payload = health.json()
    assert payload["instance_id"] == expected_instance
    assert str(payload["started_at"])[:4].isdigit()
    assert len(str(payload["config_fingerprint"])) == 64

    blocked_hosts: set[str] = set()
    console_errors: list[str] = []
    page = context.new_page()

    def route_request(route: Route) -> None:
        host = urlsplit(route.request.url).hostname or ""
        if host in LOCAL_HOSTS:
            route.continue_()
        else:
            blocked_hosts.add(host)
            route.abort("blockedbyclient")

    page.route("**/*", route_request)
    page.on(
        "console",
        lambda message: console_errors.append(message.text) if message.type == "error" else None,
    )
    yield page
    page.close()
    assert blocked_hosts == set(), f"外部network接続を試行しました: {sorted(blocked_hosts)}"
    assert console_errors == [], f"browser console errorがあります: {console_errors}"


@pytest.fixture
def streamlit_url() -> str:
    """検査対象Streamlit URLを返す。"""
    return os.environ.get("PLAYWRIGHT_STREAMLIT_URL", "http://streamlit:8501")


@pytest.fixture
def api_client() -> Iterator[httpx.Client]:
    """品質用API操作clientを返す。"""
    with httpx.Client(timeout=30) as client:
        yield client


@pytest.fixture
def screenshot_directory() -> Path:
    """公開screenshot保存先を返す。"""
    path = Path(os.environ["PLAYWRIGHT_SCREENSHOT_DIR"])
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def capture_public_screenshot(
    screenshot_directory: Path,
) -> Callable[[Page, str], Path]:
    """認証入力と画面上のemailを伏せて公開screenshotを保存する。"""

    def capture(page: Page, filename: str) -> Path:
        target = screenshot_directory / filename
        sensitive_elements = [
            page.locator('input[type="email"]'),
            page.locator('input[type="password"]'),
            page.get_by_text(re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")),
        ]
        page.screenshot(
            path=target,
            full_page=True,
            mask=sensitive_elements,
            mask_color="#737373",
        )
        return target

    return capture


__all__ = ["DEVICES", "LOCAL_HOSTS", "expect"]
