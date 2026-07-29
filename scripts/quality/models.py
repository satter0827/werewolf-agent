"""品質ゲートと実行結果の共有モデル。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from scripts._infra.process import REPOSITORY_ROOT, CommandResult
from scripts.quality.repository import ChangeSet, RepositorySnapshot

State = Literal["passed", "failed", "error", "blocked", "skipped"]
FailureState = Literal["failed", "error", "blocked"]
EnvironmentTarget = Literal["python", "quality"]
Action = Callable[["RunContext", Path], CommandResult]
CPU_INTENSIVE_RESOURCE = "cpu-intensive"


@dataclass(frozen=True, slots=True)
class QualitySettings:
    """pyproject.tomlから読む品質runner設定。"""

    max_jobs: int
    benchmark_min_rounds: int
    timeouts: dict[str, int]


@dataclass(frozen=True, slots=True)
class Gate:
    """単一の品質判定。"""

    name: str
    description: str
    command: tuple[str, ...] = ()
    cwd: Path = REPOSITORY_ROOT
    action: Action | None = None
    timeout_seconds: int | None = None
    nonzero_state: FailureState = "failed"
    dependencies: tuple[str, ...] = ()
    exclusive_resources: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    reusable: bool = False
    environment_target: EnvironmentTarget = "python"


@dataclass(slots=True)
class GateResult:
    """単一gateのレポート。"""

    name: str
    description: str
    state: State
    duration_seconds: float
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    log: str | None = None
    message: str | None = None
    artifacts: list[str] = field(default_factory=list)
    execution_origin: Literal["executed", "reused"] = "executed"
    source_run: str | None = None
    fingerprint: str | None = None


@dataclass(slots=True)
class ResourceLease:
    """品質runが所有し、終了時に解放する外部resource。"""

    name: str
    environment: dict[str, str] = field(default_factory=dict)
    cleanup_required: bool = False
    workdir: Path | None = None
    identifier: str | None = None


@dataclass(slots=True)
class RunContext:
    """1回の品質実行で共有する状態。"""

    profile: str
    jobs: int
    timeout_seconds: int
    run_id: str
    run_dir: Path
    environment: dict[str, str]
    started_at: datetime
    change: ChangeSet = field(default_factory=lambda: ChangeSet(None, None, "", None, ()))
    initial_repository_snapshot: RepositorySnapshot | None = None
    requested_profile: str | None = None
    selection_reason: str = ""
    fresh: bool = False
    initial_dependency_fingerprint: str = ""
    environment_target: EnvironmentTarget = "python"
    resources: dict[str, ResourceLease] = field(default_factory=dict)


__all__ = [
    "CPU_INTENSIVE_RESOURCE",
    "Action",
    "EnvironmentTarget",
    "FailureState",
    "Gate",
    "GateResult",
    "QualitySettings",
    "RepositorySnapshot",
    "ResourceLease",
    "RunContext",
    "State",
]
