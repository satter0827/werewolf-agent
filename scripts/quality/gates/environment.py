"""環境と外部接続制約のgate。"""

import sys
import time
from pathlib import Path

from scripts._infra.node import REQUIRED_NODE_MAJOR, node_executable, npm_executable
from scripts._infra.process import (
    ISOLATION_ENVIRONMENT,
    REPOSITORY_ROOT,
    CommandResult,
    run_command,
)
from scripts.environment.manager import PROFILES, is_ready
from scripts.quality.models import Gate, RunContext

GATES = ("environment", "isolation")


def build() -> list[Gate]:
    """依存環境と外部service隔離のgateを返す。"""
    return [
        Gate(
            "environment",
            "Reproducible dependency environment",
            ("environment-check",),
            action=check_environment,
            nonzero_state="blocked",
        ),
        Gate(
            "isolation",
            "External service isolation",
            ("isolation-environment-check",),
            action=check_isolation_environment,
        ),
    ]


def check_environment(context: RunContext, _: Path) -> CommandResult:
    """Python・Frontendの実行能力を外部接続なしで検査する。"""
    started = time.monotonic()
    profile = context.profile if context.profile in PROFILES else "check"
    try:
        ready = is_ready(profile)
    except (OSError, RuntimeError) as error:
        return CommandResult(
            ["environment-check"],
            1,
            time.monotonic() - started,
            f"環境fingerprintを検査できません: {error}\n",
        )
    if not ready:
        return CommandResult(
            ["environment-check"],
            1,
            time.monotonic() - started,
            f"{profile}環境が現在のlock・source fingerprintに対応していません。"
            f"python -m scripts.environment ensure {profile}を実行してください。\n",
        )
    npm = npm_executable()
    node = node_executable()
    commands = (
        (sys.executable, "-c", "import werewolf_agent"),
        (node, "--version"),
        (
            node,
            "-e",
            (
                "const {spawnSync}=require('node:child_process');"
                "const r=spawnSync(process.execPath,['--version']);"
                "if(r.error) console.error(r.error.stack ?? String(r.error));"
                "process.exit(r.error ? 2 : (r.status ?? 2));"
            ),
        ),
        (npm, "ls", "--depth=0", "--ignore-scripts"),
    )
    output = [f"Python {sys.version.split()[0]}\n"]
    supported_python = (3, 11) <= sys.version_info[:2] <= (3, 14)
    if not supported_python:
        return CommandResult(
            ["environment-check"],
            1,
            time.monotonic() - started,
            "".join(output) + "Python 3.11から3.14が必要です。\n",
        )
    for index, command in enumerate(commands):
        cwd = REPOSITORY_ROOT / "frontend" if index >= 1 else REPOSITORY_ROOT
        try:
            result = run_command(
                command,
                cwd=cwd,
                timeout_seconds=min(context.timeout_seconds, 60),
                environment=context.environment,
            )
        except OSError as error:
            return CommandResult(
                list(command),
                1,
                time.monotonic() - started,
                "".join(output) + f"実行環境を起動できません: {error}\n",
            )
        output.append(result.output)
        if result.returncode != 0:
            return CommandResult(
                list(command),
                result.returncode,
                time.monotonic() - started,
                "".join(output),
                result.timed_out,
            )
        if (
            index == 1
            and int(result.output.strip().lstrip("v").split(".", 1)[0]) != REQUIRED_NODE_MAJOR
        ):
            return CommandResult(
                list(command),
                1,
                time.monotonic() - started,
                "".join(output) + "Node.js 22が必要です。\n",
            )
    return CommandResult(
        ["environment-check"],
        0,
        time.monotonic() - started,
        "".join(output),
    )


def check_isolation_environment(context: RunContext, _: Path) -> CommandResult:
    """秘密情報と外部provider設定が子process環境に残らないことを検査する。"""
    started = time.monotonic()
    forbidden = [
        key
        for key in context.environment
        if key.casefold().endswith(("api_key", "token", "password", "secret"))
        and context.environment[key]
    ]
    if forbidden:
        return CommandResult(
            ["isolation-environment-check"],
            1,
            time.monotonic() - started,
            "秘密情報を含む環境変数が子processへ残っています: " + ", ".join(sorted(forbidden)),
        )
    mismatched = [
        key
        for key, expected in ISOLATION_ENVIRONMENT.items()
        if context.environment.get(key) != expected
    ]
    if mismatched:
        return CommandResult(
            ["isolation-environment-check"],
            1,
            time.monotonic() - started,
            "外部service隔離設定が一致しません: " + ", ".join(sorted(mismatched)),
        )
    return CommandResult(
        ["isolation-environment-check"],
        0,
        time.monotonic() - started,
        "外部provider用の秘密情報とtelemetryを無効化しました。\n",
    )


__all__ = ["GATES", "build", "check_environment", "check_isolation_environment"]
