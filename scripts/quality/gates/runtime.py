"""Container runtime gate。"""

import shutil
import time
from pathlib import Path

from scripts._infra.process import CommandResult, EnvironmentBlockedError, run_command
from scripts.environment.manager import RUNTIME_IMAGE
from scripts.quality.models import Gate, RunContext

GATES = ("docker",)


def build() -> list[Gate]:
    """Docker buildと非root実行のgateを返す。"""
    return [
        Gate(
            "docker",
            "Docker non-root runtime",
            tuple(docker_commands(RUNTIME_IMAGE)[0]),
            action=check_docker_runtime,
            dependencies=("environment",),
            exclusive_resources=("docker",),
        )
    ]


def docker_commands(image: str) -> tuple[list[str], ...]:
    """事前構築済みruntime imageの非root・entrypoint smokeを返す。"""
    return (
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "python",
            image,
            "-c",
            "import os, werewolf_agent; assert os.geteuid() != 0",
        ],
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "werewolf-agent-worker",
            image,
            "--help",
        ],
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "werewolf-agent",
            image,
            "--help",
        ],
    )


def check_docker_runtime(context: RunContext, _: Path) -> CommandResult:
    """事前構築済みruntime imageを外部通信なしで検査する。"""
    started = time.monotonic()
    if shutil.which("docker") is None:
        raise EnvironmentBlockedError("Docker CLIが見つかりません。")
    docker_info = run_command(
        ["docker", "info"],
        timeout_seconds=30,
        environment=context.environment,
    )
    if docker_info.returncode != 0:
        raise EnvironmentBlockedError("Docker engineが起動していません。")
    image_check = run_command(
        ["docker", "image", "inspect", RUNTIME_IMAGE],
        timeout_seconds=30,
        environment=context.environment,
    )
    if image_check.returncode != 0:
        raise EnvironmentBlockedError(
            f"品質用runtime imageがありません。初回セットアップを実行してください: {RUNTIME_IMAGE}"
        )
    commands = docker_commands(RUNTIME_IMAGE)
    output: list[str] = []
    for command in commands:
        result = run_command(
            command,
            timeout_seconds=context.timeout_seconds,
            environment=context.environment,
        )
        output.append(result.output)
        if result.returncode != 0:
            return CommandResult(
                result.command,
                result.returncode,
                time.monotonic() - started,
                "".join(output),
                result.timed_out,
            )
    return CommandResult(commands[-1], 0, time.monotonic() - started, "".join(output))


__all__ = [
    "GATES",
    "RUNTIME_IMAGE",
    "build",
    "check_docker_runtime",
    "docker_commands",
]
