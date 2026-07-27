"""Repository構造とcleanlinessのgate。"""

import sys
import time
from pathlib import Path

from scripts._infra.artifacts import LAYOUT
from scripts._infra.process import REPOSITORY_ROOT, CommandResult, run_command
from scripts.quality.models import Gate, RunContext

GATES = ("repository", "architecture", "clean-tree")


def build() -> list[Gate]:
    """Repository配置、Architecture、変更漏れのgateを返す。"""
    return [
        Gate(
            "repository",
            "Repository artifact placement",
            ("repository-artifacts",),
            action=check_artifact_placement,
        ),
        Gate(
            "architecture",
            "Architecture analysis and visualization",
            (sys.executable, "-m", "scripts.architecture"),
            artifacts=(
                "outputs/architecture/architecture.json",
                "outputs/architecture/architecture.schema.json",
                "outputs/architecture/assessment.md",
                "outputs/architecture/system-context.svg",
                "outputs/architecture/layer-dependencies.svg",
                "outputs/architecture/domain-structure.svg",
            ),
        ),
        Gate(
            "clean-tree",
            "Tracked file unchanged",
            ("git", "status", "--porcelain=v1"),
            action=check_clean_tree,
        ),
    ]


_FORBIDDEN_ROOT_ARTIFACTS = (
    ".benchmarks",
    ".coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "coverage.xml",
    "dist",
    "htmlcov",
    "site",
)
_ALLOWED_ARTIFACT_CHILDREN = frozenset(
    {"cache", "logs", "outputs", "quality", "reviews", "runtime"}
)
_ALLOWED_QUALITY_CHILDREN = frozenset({".publish.lock", "history", "profiles"})


def git_status(environment: dict[str, str]) -> str:
    """Git working treeのporcelain状態を返す。"""
    result = run_command(
        ["git", "status", "--porcelain=v1"],
        timeout_seconds=30,
        environment=environment,
    )
    if result.timed_out:
        raise RuntimeError("Git working treeの確認がtimeoutしました。")
    if result.returncode != 0:
        raise RuntimeError("Git working treeの状態を取得できませんでした。")
    return result.output


def check_clean_tree(context: RunContext, _: Path) -> CommandResult:
    """品質実行がtracked fileを変更していないことを検査する。"""
    started = time.monotonic()
    current = git_status(context.environment)
    output = ""
    if current != context.initial_git_status:
        output = "品質実行によりtracked fileが変更されました。\n" + current
    return CommandResult(
        ["git", "status", "--porcelain=v1"],
        0 if not output else 1,
        time.monotonic() - started,
        output,
    )


def check_artifact_placement(_: RunContext, __: Path) -> CommandResult:
    """Repository直下へ漏れたローカル成果物を検出する。"""
    started = time.monotonic()
    found = [name for name in _FORBIDDEN_ROOT_ARTIFACTS if (REPOSITORY_ROOT / name).exists()]
    unknown_artifacts = _unknown_children(LAYOUT.root, _ALLOWED_ARTIFACT_CHILDREN)
    unknown_quality = _unknown_children(LAYOUT.quality, _ALLOWED_QUALITY_CHILDREN)
    output: list[str] = []
    if found:
        output.append("Repository直下に禁止した成果物があります:\n")
        output.extend(f"- {name}\n" for name in found)
    if unknown_artifacts:
        output.append(".werewolf-agent直下に未定義の領域があります:\n")
        output.extend(f"- {name}\n" for name in unknown_artifacts)
    if unknown_quality:
        output.append("quality直下に未定義の領域があります:\n")
        output.extend(f"- {name}\n" for name in unknown_quality)
    message = "".join(output)
    return CommandResult(
        ["repository-artifacts"],
        1 if message else 0,
        time.monotonic() - started,
        message,
    )


def _unknown_children(root: Path, allowed: frozenset[str]) -> list[str]:
    """管理root直下の未定義entry名を返す。"""
    if not root.is_dir():
        return []
    return sorted(
        entry.name
        for entry in root.iterdir()
        if entry.name not in allowed and not entry.name.startswith(".publish.lock.")
    )


__all__ = [
    "GATES",
    "build",
    "check_artifact_placement",
    "check_clean_tree",
    "git_status",
]
