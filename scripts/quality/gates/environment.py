"""環境と外部接続制約のgate。"""

import sys
import time
from pathlib import Path

from scripts._infra.process import (
    ISOLATION_ENVIRONMENT,
    CommandResult,
    run_command,
)
from scripts.environment.manager import inspect_environment
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
            nonzero_state="error",
        ),
        Gate(
            "isolation",
            "External service isolation",
            ("isolation-environment-check",),
            action=check_isolation_environment,
        ),
    ]


def check_environment(context: RunContext, _: Path) -> CommandResult:
    """Lockに対応するPython実行能力を外部接続なしで検査する。"""
    started = time.monotonic()
    target = getattr(context, "environment_target", "python")
    try:
        report = inspect_environment(target)
    except (OSError, RuntimeError) as error:
        return CommandResult(
            ["environment-check"],
            1,
            time.monotonic() - started,
            f"環境fingerprintを検査できません: {error}\n",
        )
    if report.state != "passed":
        detail = report.confirmed_causes[0] if report.confirmed_causes else "環境が未準備です。"
        return CommandResult(
            ["environment-check"],
            1 if report.state == "error" else 2,
            time.monotonic() - started,
            f"{detail} python -m scripts.environment setup {target}を実行してください。\n",
        )
    commands = ((sys.executable, "-c", "import werewolf_agent"),)
    output = [f"Python {sys.version.split()[0]}\n"]
    for command in commands:
        try:
            result = run_command(
                command,
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
