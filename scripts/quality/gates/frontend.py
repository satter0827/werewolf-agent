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
            action=_test_action,
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
        if result.returncode != 0 and _native_binding_blocked(result.output):
            result = _run_in_e2e_image(
                context,
                ("npm", "run", "build:quality", "--", "--outDir", "/output", "--emptyOutDir"),
                output_directory=staging,
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


def _test_action(context: RunContext, _: Path) -> CommandResult:
    """Host実行を優先し、native moduleのpolicy拒否時だけLinux imageへ移す。"""
    npm = npm_executable()
    result = run_command(
        [npm, "test"],
        cwd=REPOSITORY_ROOT / "frontend",
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
    )
    if result.returncode == 0 or not _native_binding_blocked(result.output):
        return result
    return _run_in_e2e_image(context, ("npm", "test"))


def _run_in_e2e_image(
    context: RunContext,
    command: tuple[str, ...],
    *,
    output_directory: Path | None = None,
) -> CommandResult:
    """現在sourceからimageを作り、外部serviceなしでFrontend commandを実行する。"""
    started = time.monotonic()
    build_command = ["docker", "compose", "--profile", "e2e", "build", "e2e"]
    built = run_command(
        build_command,
        cwd=REPOSITORY_ROOT,
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
    )
    if built.returncode != 0:
        return built
    run = [
        "docker",
        "compose",
        "--profile",
        "e2e",
        "run",
        "--rm",
        "--no-deps",
        "--pull",
        "never",
    ]
    if output_directory is not None:
        run.extend(("--volume", f"{output_directory.resolve()}:/output"))
    run.extend(("e2e", *command))
    result = run_command(
        run,
        cwd=REPOSITORY_ROOT,
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
    )
    return CommandResult(
        result.command,
        result.returncode,
        time.monotonic() - started,
        built.output + result.output,
    )


def _native_binding_blocked(output: str) -> bool:
    lowered = output.casefold()
    return "application control policy has blocked" in lowered or (
        "アプリケーション制御ポリシー" in output and "ブロック" in output
    )


__all__ = ["BUILD_GATES", "GATES", "STATIC_GATES", "build"]
