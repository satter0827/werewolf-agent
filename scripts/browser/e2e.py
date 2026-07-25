"""事前構築済みDocker imageでReactとStreamlitのE2Eを実行する。"""

from __future__ import annotations

import argparse
import os
import shutil
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from scripts._infra.process import (
    ARTIFACT_ROOT,
    QUALITY_COMPOSE_PROJECT_NAME,
    CommandResult,
    EnvironmentBlockedError,
    quality_environment,
    run_command,
)

_REQUIRED_ENVIRONMENT = (
    "WEREWOLF_SUPABASE_DB_DSN",
    "WEREWOLF_SUPABASE_PUBLISHABLE_KEY",
    "WEREWOLF_SUPABASE_URL",
)
_SERVICES = ("api", "worker", "frontend-e2e", "streamlit", "e2e")


def run_e2e(
    *,
    base_environment: Mapping[str, str],
    artifact_directory: Path,
    timeout_seconds: int,
    visual_regression: bool,
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
    output: list[str] = []
    commands = _commands(artifact_directory)
    try:
        for command in commands:
            result = run_command(
                command,
                timeout_seconds=timeout_seconds,
                environment=environment,
            )
            output.append(result.output)
            if result.returncode != 0:
                return CommandResult(
                    command=list(command),
                    returncode=result.returncode,
                    duration_seconds=time.monotonic() - started,
                    output="".join(output),
                    timed_out=result.timed_out,
                )
    finally:
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
    return CommandResult(
        command=list(commands[-1]),
        returncode=cleanup.returncode,
        duration_seconds=time.monotonic() - started,
        output="".join(output),
        timed_out=cleanup.timed_out,
    )


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
        "VITE_SUPABASE_PUBLISHABLE_KEY": str(base_environment["WEREWOLF_SUPABASE_PUBLISHABLE_KEY"]),
        "VITE_SUPABASE_URL": container_api_url,
        "VITE_WEREWOLF_API_URL": "http://api:8000",
        "WEREWOLF_API_RATE_LIMIT_REQUESTS": "1000",
        "WEREWOLF_API_CORS_ORIGINS": (
            "http://localhost:5173,http://localhost:8080,http://frontend-e2e:8080"
        ),
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


def _commands(artifact_directory: Path) -> tuple[tuple[str, ...], ...]:
    """buildやpullを許可しないE2E command列を返す。"""
    mount = f"{artifact_directory.resolve()}:/tmp/werewolf-agent/playwright"
    return (
        (
            "docker",
            "compose",
            "--profile",
            "e2e",
            "run",
            "--rm",
            "--no-deps",
            "--pull",
            "never",
            "migrate",
        ),
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
            "api",
            "worker",
            "frontend-e2e",
            "streamlit",
        ),
        (
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
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    """CLI parserを返す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=ARTIFACT_ROOT / "qa" / "browser",
    )
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--visual-regression", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """現在の安全な環境でE2Eを実行する。"""
    arguments = build_parser().parse_args(argv)
    if arguments.timeout < 1:
        raise SystemExit("--timeoutには1以上を指定してください。")
    try:
        result = run_e2e(
            base_environment=os.environ,
            artifact_directory=arguments.artifacts,
            timeout_seconds=arguments.timeout,
            visual_regression=arguments.visual_regression,
        )
    except (EnvironmentBlockedError, ValueError) as error:
        print(str(error))
        return 2
    print(result.output, end="")
    return 0 if result.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
