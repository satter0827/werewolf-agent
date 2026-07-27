"""事前構築済みPython imageでStreamlitのBrowser E2Eを実行する。"""

from __future__ import annotations

import argparse
import os
import shutil
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from PIL import Image, ImageDraw

from scripts._infra.operations import (
    operation_run_id,
    prune_review_runs,
    write_bundle_manifest,
)
from scripts._infra.process import (
    ARTIFACT_ROOT,
    QUALITY_COMPOSE_PROJECT_NAME,
    CommandResult,
    EnvironmentBlockedError,
    quality_environment,
    redact,
    run_command,
    write_json,
)
from scripts.browser.catalog import capture_filenames, load_catalog, scenario_expression

_REQUIRED_ENVIRONMENT = (
    "WEREWOLF_SUPABASE_DB_DSN",
    "WEREWOLF_SUPABASE_PUBLISHABLE_KEY",
    "WEREWOLF_SUPABASE_URL",
)
_SERVICES = ("api", "worker", "streamlit", "e2e")


def run_e2e(
    *,
    base_environment: Mapping[str, str],
    artifact_directory: Path,
    timeout_seconds: int,
    visual_regression: bool,
    suite: str = "streamlit",
    journey: str | None = None,
    state: str | None = None,
    devices: Sequence[str] = ("desktop", "mobile"),
    captures: Sequence[str] = (),
    trace: str = "failure",
) -> CommandResult:
    """品質専用Compose projectでbrowser E2Eを実行する。"""
    started = time.monotonic()
    if shutil.which("docker") is None:
        raise EnvironmentBlockedError("Docker CLIが見つかりません。")
    missing = [name for name in _REQUIRED_ENVIRONMENT if not base_environment.get(name)]
    if missing:
        raise EnvironmentBlockedError("E2Eに必要なSupabase設定がありません: " + ", ".join(missing))

    artifact_directory.mkdir(parents=True, exist_ok=True)
    environment = _compose_environment(
        base_environment,
        visual_regression=visual_regression,
    )
    selected_devices = tuple(devices)
    selected_captures = tuple(captures)
    environment["PLAYWRIGHT_DEVICES"] = ",".join(selected_devices)
    environment["PLAYWRIGHT_CAPTURES"] = ",".join(
        capture_filenames(selected_captures, selected_devices)
    )
    environment["PLAYWRIGHT_TRACE"] = "always" if trace == "always" else "failure"
    output: list[str] = []
    commands = _commands(
        artifact_directory,
        suite=suite,
        scenario_filter=scenario_expression(journey, state, selected_captures),
    )
    initial_cleanup = run_command(
        ["docker", "compose", "--profile", "e2e", "down", "--volumes", "--remove-orphans"],
        timeout_seconds=60,
        environment=environment,
    )
    output.append(initial_cleanup.output)
    before = _owned_resource_snapshot(environment)
    execution = CommandResult([], 0, 0.0, "")
    try:
        for command in commands:
            execution = run_command(
                command,
                timeout_seconds=timeout_seconds,
                environment=environment,
            )
            output.append(execution.output)
            if execution.returncode != 0:
                break
        create_contact_sheet(artifact_directory / "public")
    finally:
        service_log_root = artifact_directory / "logs"
        service_log_root.mkdir(parents=True, exist_ok=True)
        for service in ("migrate", "api", "worker", "streamlit"):
            service_log = run_command(
                [
                    "docker",
                    "compose",
                    "--profile",
                    "e2e",
                    "logs",
                    "--no-color",
                    "--no-log-prefix",
                    service,
                ],
                timeout_seconds=60,
                environment=environment,
            )
            (service_log_root / f"{service}.log").write_text(
                redact(service_log.output), encoding="utf-8"
            )
            if execution.returncode != 0:
                output.append(f"\n--- {service} logs ---\n")
                output.append(service_log.output)
        cleanup = run_command(
            [
                "docker",
                "compose",
                "--profile",
                "e2e",
                "down",
                "--volumes",
                "--remove-orphans",
            ],
            timeout_seconds=60,
            environment=environment,
        )
        output.append(cleanup.output)
        after = _owned_resource_snapshot(environment)
        write_json(artifact_directory / "docker-before.json", before)
        write_json(artifact_directory / "docker-after.json", after)
        if after["containers"] or after["volumes"]:
            output.append(f"品質所有Docker resourceが残っています: {after}\n")
            cleanup = CommandResult(
                cleanup.command,
                1,
                cleanup.duration_seconds,
                cleanup.output,
                cleanup.timed_out,
            )
    return CommandResult(
        command=execution.command or list(commands[-1]),
        returncode=execution.returncode or cleanup.returncode,
        duration_seconds=time.monotonic() - started,
        output="".join(output),
        timed_out=execution.timed_out or cleanup.timed_out,
    )


def _owned_resource_snapshot(environment: Mapping[str, str]) -> dict[str, list[str]]:
    """Compose project labelで品質所有resourceだけを列挙する。"""
    label = f"com.docker.compose.project={QUALITY_COMPOSE_PROJECT_NAME}"
    containers = run_command(
        ["docker", "ps", "-a", "--filter", f"label={label}", "--format", "{{.ID}}"],
        timeout_seconds=30,
        environment=environment,
    )
    volumes = run_command(
        ["docker", "volume", "ls", "--filter", f"label={label}", "--format", "{{.Name}}"],
        timeout_seconds=30,
        environment=environment,
    )
    failures = [result for result in (containers, volumes) if result.returncode != 0]
    if failures:
        details = "\n".join(result.output.strip() for result in failures if result.output.strip())
        raise EnvironmentBlockedError(
            "品質所有Docker resourceを確認できませんでした。" + (f"\n{details}" if details else "")
        )
    return {
        "containers": sorted(line for line in containers.output.splitlines() if line.strip()),
        "volumes": sorted(line for line in volumes.output.splitlines() if line.strip()),
    }


def create_contact_sheet(public_directory: Path) -> Path | None:
    """公開screenshotだけを人間レビュー用の一覧画像へまとめる。"""
    screenshot_directory = public_directory / "screenshots"
    images = sorted(
        path for path in screenshot_directory.glob("*.png") if path.name != "contact-sheet.png"
    )
    if not images:
        return None
    columns = 2
    cell_width = 520
    thumbnail_height = 520
    label_height = 40
    thumbnails: list[tuple[Path, Image.Image]] = []
    for path in images:
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((cell_width, thumbnail_height))
            thumbnails.append((path, image.copy()))
    row_height = label_height + thumbnail_height
    row_count = (len(thumbnails) + columns - 1) // columns
    width = cell_width * columns
    sheet = Image.new("RGB", (width, row_height * row_count), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (path, image) in enumerate(thumbnails):
        column = index % columns
        row = index // columns
        left = column * cell_width
        top = row * row_height
        draw.text(
            (left + 8, top + 8),
            path.relative_to(public_directory).as_posix(),
            fill="black",
        )
        sheet.paste(image, (left + (cell_width - image.width) // 2, top + label_height))
    target = public_directory / "contact-sheet.png"
    sheet.save(target)
    return target


def _compose_environment(
    base_environment: Mapping[str, str],
    *,
    visual_regression: bool,
) -> dict[str, str]:
    """host接続値を品質専用Compose service向けに変換する。"""
    api_url = str(base_environment["WEREWOLF_SUPABASE_URL"])
    database_dsn = str(base_environment["WEREWOLF_SUPABASE_DB_DSN"])
    container_api_url = _replace_host(api_url, "host.docker.internal")
    container_database_dsn = _replace_host(database_dsn, "host.docker.internal")
    extra = {
        "COMPOSE_PROJECT_NAME": QUALITY_COMPOSE_PROJECT_NAME,
        "PLAYWRIGHT_VISUAL_REGRESSION": "1" if visual_regression else "0",
        "PLAYWRIGHT_OUTPUT_DIR": "/tmp/werewolf-agent/playwright",
        "PLAYWRIGHT_SCREENSHOT_DIR": "/tmp/werewolf-agent/playwright/public/screenshots",
        "WEREWOLF_API_INSTANCE_ID": f"quality-{uuid4().hex}",
        "PLAYWRIGHT_API_URL": "http://api:8000",
        "PLAYWRIGHT_STREAMLIT_URL": "http://streamlit:8501",
        "PLAYWRIGHT_SUPABASE_PUBLISHABLE_KEY": str(
            base_environment["WEREWOLF_SUPABASE_PUBLISHABLE_KEY"]
        ),
        "PLAYWRIGHT_SUPABASE_URL": container_api_url,
        # Browser E2Eは製品のrate limitを検査しないため、固定の余裕を持たせる。
        "WEREWOLF_API_RATE_LIMIT_REQUESTS": "10000",
        "WEREWOLF_COMPOSE_SUPABASE_DB_DSN": container_database_dsn,
        "WEREWOLF_SUPABASE_JWKS_URL": (
            f"{container_api_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        ),
        "WEREWOLF_SUPABASE_JWT_ISSUER": f"{api_url.rstrip('/')}/auth/v1",
        "WEREWOLF_SUPABASE_PUBLISHABLE_KEY": str(
            base_environment["WEREWOLF_SUPABASE_PUBLISHABLE_KEY"]
        ),
        "WEREWOLF_SUPABASE_URL": container_api_url,
    }
    return quality_environment(extra={**dict(base_environment), **extra})


def _replace_host(url: str, host: str) -> str:
    """URLまたはDSNのhostだけを置き換える。"""
    parsed = urlsplit(url)
    if parsed.hostname is None:
        raise ValueError(f"hostを含むURLを指定してください: {url}")
    userinfo = ""
    if parsed.username is not None:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return urlunsplit(
        (
            parsed.scheme,
            f"{userinfo}{host}{port}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def _commands(
    artifact_directory: Path,
    *,
    suite: str = "streamlit",
    scenario_filter: str | None = None,
) -> tuple[tuple[str, ...], ...]:
    """buildやpullを許可しないE2E command列を返す。"""
    if suite not in {"streamlit", "local-llm"}:
        raise ValueError(f"未定義のBrowser suiteです: {suite}")
    mount = f"{artifact_directory.resolve()}:/tmp/werewolf-agent/playwright"
    scenario = (
        "scripts/browser/scenarios/test_streamlit.py"
        if suite == "streamlit"
        else "scripts/browser/scenarios/test_local_llm.py"
    )
    pytest_command = [
        "docker",
        "compose",
        "--profile",
        "e2e",
        "run",
        "--rm",
        "--no-deps",
        "--pull",
        "never",
        "--volume",
        mount,
        "e2e",
        "python",
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "--browser",
        "chromium",
        "--tracing",
        "off",
        "--screenshot",
        "only-on-failure",
        "--output",
        "/tmp/werewolf-agent/playwright/private/playwright",
        "--junitxml",
        "/tmp/werewolf-agent/playwright/results.xml",
        "--json-report",
        "--json-report-file",
        "/tmp/werewolf-agent/playwright/results.json",
        "--html",
        "/tmp/werewolf-agent/playwright/html/index.html",
        "--self-contained-html",
    ]
    if scenario_filter:
        pytest_command.extend(("-k", scenario_filter))
    pytest_command.append(scenario)
    return (
        (
            "docker",
            "compose",
            "--profile",
            "e2e",
            "up",
            "-d",
            "--wait",
            "--no-build",
            "--pull",
            "never",
            "migrate",
            "api",
            "worker",
            "streamlit",
        ),
        tuple(pytest_command),
    )


def build_parser() -> argparse.ArgumentParser:
    """CLI parserを返す。"""
    catalog = load_catalog()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts",
        type=Path,
    )
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--visual-regression", action="store_true")
    parser.add_argument("--suite", choices=("streamlit", "local-llm"), default="streamlit")
    parser.add_argument("--journey", choices=tuple(catalog["journeys"]))
    parser.add_argument("--state", choices=tuple(catalog["states"]))
    parser.add_argument(
        "--device",
        action="append",
        choices=tuple(catalog["devices"]),
        dest="devices",
    )
    parser.add_argument(
        "--capture",
        action="append",
        choices=tuple(catalog["captures"]),
        default=[],
        dest="captures",
    )
    parser.add_argument("--trace", choices=("failure", "always"), default="failure")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """現在の安全な環境でE2Eを実行する。"""
    arguments = build_parser().parse_args(argv)
    if arguments.timeout < 1:
        raise SystemExit("--timeoutには1以上を指定してください。")
    artifact_directory = arguments.artifacts or (
        ARTIFACT_ROOT / "reviews" / "browser" / operation_run_id("browser")
    )
    artifact_directory.mkdir(parents=True, exist_ok=True)
    (artifact_directory / ".active").write_text("", encoding="utf-8")
    state = "error"
    message = "Browser E2Eで予期しない実行失敗が発生しました。"
    return_code = 1
    try:
        result = run_e2e(
            base_environment=os.environ,
            artifact_directory=artifact_directory,
            timeout_seconds=arguments.timeout,
            visual_regression=arguments.visual_regression,
            suite=arguments.suite,
            journey=arguments.journey,
            state=arguments.state,
            devices=arguments.devices or ("desktop", "mobile"),
            captures=arguments.captures,
            trace=arguments.trace,
        )
    except (EnvironmentBlockedError, ValueError) as error:
        state = "blocked"
        message = str(error)
        return_code = 2
    except Exception as error:
        message = redact(str(error)) or message
    else:
        print(result.output, end="")
        state = "passed" if result.returncode == 0 else "failed"
        message = (
            "Browser E2Eが完了しました。" if state == "passed" else "Browser E2Eに失敗しました。"
        )
        return_code = 0 if result.returncode == 0 else 1
    if return_code != 0:
        print(message)
    write_json(
        artifact_directory / "report.json",
        {
            "schema_version": 1,
            "run_id": artifact_directory.name,
            "kind": "browser",
            "state": state,
            "confirmed_causes": [message] if state in {"blocked", "error"} else [],
            "unconfirmed_scope": [] if state == "passed" else ["失敗後のscenarioは未確認です。"],
            "next_actions": []
            if state == "passed"
            else ["reportとservice logを確認してください。"],
        },
    )
    (artifact_directory / "summary.md").write_text(
        f"# Browser E2E\n\n- 判定: `{state}`\n- 状況: {message}\n",
        encoding="utf-8",
    )
    write_bundle_manifest(artifact_directory)
    (artifact_directory / ".active").unlink(missing_ok=True)
    prune_review_runs()
    print(f"Browser review: {artifact_directory}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
