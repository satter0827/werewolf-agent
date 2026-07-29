"""Repository構造のgate。"""

import sys
import time
from pathlib import Path

from scripts._infra.artifacts import LAYOUT
from scripts._infra.process import REPOSITORY_ROOT, CommandResult, run_command
from scripts.quality.models import Gate, RunContext

GATES = ("repository", "version-contract", "architecture")


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
            "version-contract",
            "Version ownership contract",
            (sys.executable, "-m", "scripts.versioning", "check"),
            action=check_version_contract,
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
    {"cache", "diagnostics", "logs", "operations", "outputs", "quality", "reviews", "runtime"}
)
_ALLOWED_QUALITY_CHILDREN = frozenset({".publish.lock", "history", "profiles"})


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


def check_version_contract(context: RunContext, _: Path) -> CommandResult:
    """品質実行と同じbase、headでversion所有境界を検査する。"""
    command = [sys.executable, "-m", "scripts.versioning", "check"]
    if context.change.base_ref is not None:
        command.extend(("--base-ref", context.change.base_ref))
    command.extend(("--head-ref", context.change.head_ref))
    return run_command(
        command,
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
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
    "check_version_contract",
]
