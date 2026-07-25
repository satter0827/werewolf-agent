"""品質ゲートと実行結果の共有モデル。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from scripts._infra.process import REPOSITORY_ROOT, CommandResult

State = Literal["passed", "failed", "error", "blocked", "skipped"]
FailureState = Literal["failed", "error", "blocked"]
Action = Callable[["RunContext", Path], CommandResult]


@dataclass(frozen=True, slots=True)
class QualitySettings:
    """pyproject.tomlから読む品質runner設定。"""

    max_jobs: int
    benchmark_min_rounds: int
    benchmark_max_mean_ms: int
    coverage_fail_under: int
    branch_coverage_fail_under: int
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


@dataclass(slots=True)
class RunContext:
    """1回の品質実行で共有する状態。"""

    profile: str
    jobs: int
    timeout_seconds: int
    run_id: str
    run_dir: Path
    environment: dict[str, str]
    initial_git_status: str
    started_at: datetime
    supabase_environment: dict[str, str] = field(default_factory=dict)
    supabase_cleanup_required: bool = False
    supabase_workdir: Path | None = None
    supabase_project_id: str | None = None


__all__ = [
    "Action",
    "FailureState",
    "Gate",
    "GateResult",
    "QualitySettings",
    "RunContext",
    "State",
]
