"""Frontend静的検査とbuild gate。"""

import time
from pathlib import Path

from scripts._infra.artifacts import LAYOUT, publish_directory, staged_directory
from scripts._infra.node import npm_executable
from scripts._infra.process import REPOSITORY_ROOT, CommandResult, run_command
from scripts.quality.models import Gate, RunContext

STATIC_GATES = ("eslint", "prettier", "typescript")
BUILD_GATES = ("frontend-build",)
GATES = (*STATIC_GATES, *BUILD_GATES)


def build() -> list[Gate]:
    """package.jsonのscriptだけを呼ぶFrontend gateを返す。"""
    npm = npm_executable()
    cwd = REPOSITORY_ROOT / "frontend"
    return [
        Gate(
            "eslint",
            "Frontend lint",
            (npm, "run", "lint"),
            cwd=cwd,
            dependencies=("environment",),
            exclusive_resources=("frontend-workspace",),
        ),
        Gate(
            "prettier",
            "Frontend format",
            (npm, "run", "format:check"),
            cwd=cwd,
            dependencies=("environment",),
            exclusive_resources=("frontend-workspace",),
        ),
        Gate(
            "typescript",
            "TypeScript type check",
            (npm, "run", "typecheck"),
            cwd=cwd,
            dependencies=("environment",),
            exclusive_resources=("frontend-workspace",),
        ),
        Gate(
            "vitest",
            "Frontend unit test",
            (npm, "test"),
            cwd=cwd,
            dependencies=("environment",),
            exclusive_resources=("frontend-workspace",),
        ),
        Gate(
            "frontend-build",
            "Frontend production build",
            (npm, "run", "build:quality"),
            cwd=cwd,
            action=_build_action,
            dependencies=("environment",),
            exclusive_resources=("frontend-workspace",),
            artifacts=("build/frontend/index.html",),
        ),
    ]


def _build_action(context: RunContext, _: Path) -> CommandResult:
    """Frontendをscratchで構築し、成功時だけ公開する。"""
    started = time.monotonic()
    npm = npm_executable()
    with staged_directory("frontend") as staging:
        command = [
            npm,
            "run",
            "build:quality",
            "--",
            "--outDir",
            str(staging),
            "--emptyOutDir",
        ]
        result = run_command(
            command,
            cwd=REPOSITORY_ROOT / "frontend",
            timeout_seconds=context.timeout_seconds,
            environment=context.environment,
        )
        if result.returncode != 0:
            return result
        if not (staging / "index.html").is_file():
            return CommandResult(
                command,
                1,
                time.monotonic() - started,
                result.output + "Frontend buildにindex.htmlがありません。\n",
            )
        publish_directory(staging, LAYOUT.build / "frontend")
        return CommandResult(
            command,
            0,
            time.monotonic() - started,
            result.output,
        )


__all__ = ["BUILD_GATES", "GATES", "STATIC_GATES", "build"]
