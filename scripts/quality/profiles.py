"""品質profileと意味単位selectorを定義する。"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from scripts.quality.gates import browser as browser_module
from scripts.quality.gates import contracts as contracts_module
from scripts.quality.gates import distribution as distribution_module
from scripts.quality.gates import documentation as documentation_module
from scripts.quality.gates import environment as environment_module
from scripts.quality.gates import python as python_module
from scripts.quality.gates import repository as repository_module
from scripts.quality.gates import runtime as runtime_module
from scripts.quality.gates import services as services_module
from scripts.quality.gates import tests as tests_module
from scripts.quality.gates.browser import GATES as BROWSER_GATES
from scripts.quality.gates.contracts import GATES as CONTRACT_GATES
from scripts.quality.gates.distribution import BENCHMARK_GATES, PACKAGE_GATES
from scripts.quality.gates.documentation import GATES as DOCS_GATES
from scripts.quality.gates.python import GATES as PYTHON_STATIC_GATES
from scripts.quality.gates.runtime import GATES as RUNTIME_GATES
from scripts.quality.gates.services import GATES as SERVICE_GATES
from scripts.quality.gates.tests import DEEP_GATES, INTEGRATION_GATES, UNIT_GATES
from scripts.quality.models import Gate, QualitySettings

PROFILE_ORDER = ("focus", "check", "release", "deep")

GROUPS: dict[str, tuple[str, ...]] = {
    "python-static": ("repository", "version-contract", "architecture", *PYTHON_STATIC_GATES),
    "unit": UNIT_GATES,
    "docs": DOCS_GATES,
    "contracts": CONTRACT_GATES,
    "distribution": PACKAGE_GATES,
    "benchmark": BENCHMARK_GATES,
    "integration": (*PACKAGE_GATES, *INTEGRATION_GATES, *SERVICE_GATES),
    "browser": ("supabase-cleanup", "supabase-preflight", *BROWSER_GATES),
    "runtime": RUNTIME_GATES,
}


def build_profile(
    profile: str,
    *,
    run_dir: Path,
    settings: QualitySettings,
    jobs: int,
    fresh: bool = False,
) -> list[list[Gate]]:
    """担当moduleのgateからprofileを構築し、schedulerでstageを導出する。"""
    from scripts.quality.scheduler import select_stages

    catalog = build_catalog(
        profile,
        run_dir=run_dir,
        settings=settings,
        jobs=jobs,
        fresh=fresh,
    )
    focus = {
        "environment",
        "repository",
        "version-contract",
        "architecture",
        *PYTHON_STATIC_GATES,
        *UNIT_GATES,
        "isolation",
    }
    check = {
        *focus,
        "docs",
        "openapi",
        *INTEGRATION_GATES,
        "package",
    }
    release = {
        *check,
        "supabase-preflight",
        "supabase-lint",
        "supabase-integration",
        "e2e",
        "docker",
    }
    names = {
        "focus": focus,
        "check": check,
        "release": release,
        "deep": {*release, *DEEP_GATES, "benchmark"},
    }[profile]
    return select_stages([catalog], sorted(names), expand_groups=False)


def build_catalog(
    profile: str,
    *,
    run_dir: Path,
    settings: QualitySettings,
    jobs: int,
    fresh: bool = False,
) -> list[Gate]:
    """Selector実行にも使う全gate catalogを返す。"""
    return [
        *environment_module.build(),
        *repository_module.build(),
        *python_module.build(fresh=fresh),
        *tests_module.build(run_dir, settings, jobs, profile=profile),
        *documentation_module.build(),
        *contracts_module.build(),
        *distribution_module.build(run_dir, settings),
        *services_module.build(run_dir),
        *browser_module.build(),
        *runtime_module.build(),
    ]


def expand_selectors(selectors: Iterable[str], available: set[str]) -> set[str]:
    """意味単位と個別gateを展開する。"""
    selected: set[str] = set()
    for selector in selectors:
        names = GROUPS.get(selector, (selector,))
        unknown = set(names) - available
        if unknown:
            raise ValueError(f"未定義の品質gateです: {', '.join(sorted(unknown))}")
        selected.update(names)
    return selected


__all__ = [
    "GROUPS",
    "PROFILE_ORDER",
    "build_catalog",
    "build_profile",
    "expand_selectors",
]
