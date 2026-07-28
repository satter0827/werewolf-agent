"""Python Playwright scenarioの共有fixture。"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Generator, Iterator
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import httpx
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, Route, expect

from scripts.browser.catalog import load_catalog

LOCAL_HOSTS = frozenset(
    {"127.0.0.1", "::1", "api", "host.docker.internal", "localhost", "streamlit"}
)

DEVICES = {key: str(value) for key, value in load_catalog()["devices"].items()}
_REPORTS = pytest.StashKey[dict[str, pytest.TestReport]]()


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """CLIから選択されたdeviceだけをscenarioへ適用する。"""
    if "device_name" not in metafunc.fixturenames:
        return
    requested = os.environ.get("PLAYWRIGHT_DEVICES", "desktop,mobile").split(",")
    devices = [name.strip() for name in requested if name.strip()]
    unknown = set(devices) - set(DEVICES)
    if unknown:
        raise pytest.UsageError(f"未定義のBrowser deviceです: {sorted(unknown)}")
    metafunc.parametrize("device_name", devices)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(
    item: pytest.Item,
    call: pytest.CallInfo[None],
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """Scenario失敗状態をtrace fixtureへ渡す。"""
    report = yield
    reports = item.stash.setdefault(_REPORTS, {})
    reports[report.when] = report
    return report


@pytest.fixture
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
    request: pytest.FixtureRequest,
) -> Iterator[BrowserContext]:
    """各scenarioを独立contextに分離し、失敗時だけtraceを保存する。"""
    context = browser.new_context(**cast(Any, browser_context_args))
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    try:
        yield context
    finally:
        failed = any(report.failed for report in request.node.stash.get(_REPORTS, {}).values())
        if failed or os.environ.get("PLAYWRIGHT_TRACE") == "always":
            trace = Path(output_path) / "trace.zip"
            trace.parent.mkdir(parents=True, exist_ok=True)
            context.tracing.stop(path=trace)
        else:
            context.tracing.stop()
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


@pytest.fixture(scope="session")
def degraded_streamlit_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """必須接続情報がない縮退画面を独立processで起動する。"""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])

    log_directory = tmp_path_factory.mktemp("degraded-streamlit")
    stdout_path = log_directory / "stdout.log"
    stderr_path = log_directory / "stderr.log"
    environment = os.environ.copy()
    environment.pop("WEREWOLF_SUPABASE_URL", None)
    environment.pop("WEREWOLF_SUPABASE_PUBLISHABLE_KEY", None)
    environment["WEREWOLF_API_BASE_URL"] = "http://127.0.0.1:9"
    source_path = str(Path.cwd() / "src")
    current_python_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (source_path, current_python_path) if part
    )
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "src/werewolf_agent/clients/streamlit/app.py",
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    with (
        stdout_path.open("w", encoding="utf-8") as stdout,
        stderr_path.open("w", encoding="utf-8") as stderr,
    ):
        process = subprocess.Popen(command, env=environment, stdout=stdout, stderr=stderr)
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(
                    "縮退画面のStreamlit起動に失敗しました: "
                    f"{stderr_path.read_text(encoding='utf-8')}"
                )
            try:
                if httpx.get(f"{url}/_stcore/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            process.terminate()
            raise AssertionError("縮退画面のStreamlit起動がtimeoutしました")
        try:
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


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
        selected = {
            value.strip()
            for value in os.environ.get("PLAYWRIGHT_CAPTURES", "").split(",")
            if value.strip()
        }
        if selected and filename not in selected and Path(filename).stem not in selected:
            return target
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
