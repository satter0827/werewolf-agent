"""環境と外部接続制約のgate。"""

import shutil
import sys
import time
from pathlib import Path

from scripts._infra.process import (
    OFFLINE_GUARD_ENVIRONMENT,
    REPOSITORY_ROOT,
    CommandResult,
    run_command,
)
from scripts.quality.models import Gate, RunContext

GATES = ("environment", "offline")


def build() -> list[Gate]:
    """依存環境とoffline制約のgateを返す。"""
    return [
        Gate(
            "environment",
            "Reproducible dependency environment",
            ("environment-check",),
            action=check_environment,
            nonzero_state="blocked",
        ),
        Gate(
            "offline",
            "Offline environment",
            ("offline-environment-check",),
            action=check_offline_environment,
        ),
    ]


def check_environment(context: RunContext, _: Path) -> CommandResult:
    """Lock fileに対するPython・Frontend依存の同期状態を検査する。"""
    started = time.monotonic()
    npm = shutil.which("npm") or "npm"
    node = shutil.which("node") or "node"
    commands = (
        ("uv", "sync", "--check", "--frozen", "--all-groups", "--all-extras"),
        (node, "--version"),
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
        result = run_command(
            command,
            cwd=cwd,
            timeout_seconds=min(context.timeout_seconds, 60),
            environment=context.environment,
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
        if index == 1 and not result.output.strip().lstrip("v").startswith("22."):
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


def check_offline_environment(context: RunContext, _: Path) -> CommandResult:
    """秘密情報と外部通信防止設定が子process環境に残らないことを検査する。"""
    started = time.monotonic()
    forbidden = [
        key
        for key in context.environment
        if key.casefold().endswith(("api_key", "token", "password", "secret"))
        and context.environment[key]
    ]
    if forbidden:
        return CommandResult(
            ["offline-environment-check"],
            1,
            time.monotonic() - started,
            "秘密情報を含む環境変数が子processへ残っています: " + ", ".join(sorted(forbidden)),
        )
    mismatched = [
        key
        for key, expected in OFFLINE_GUARD_ENVIRONMENT.items()
        if context.environment.get(key) != expected
    ]
    if mismatched:
        return CommandResult(
            ["offline-environment-check"],
            1,
            time.monotonic() - started,
            "外部通信防止設定が一致しません: " + ", ".join(sorted(mismatched)),
        )
    return CommandResult(
        ["offline-environment-check"],
        0,
        time.monotonic() - started,
        "外部provider用の秘密情報とtelemetryを無効化しました。\n",
    )


__all__ = ["GATES", "build", "check_environment", "check_offline_environment"]
