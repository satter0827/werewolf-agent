"""品質gate selectorとschedulerの契約。"""

from pathlib import Path

import pytest
from scripts.quality.models import Gate
from scripts.quality.profiles import expand_selectors
from scripts.quality.runner import _profile_stages
from scripts.quality.scheduler import select_stages


def test_meaningful_selector_expands_without_coupling_to_profile() -> None:
    """意味単位を個別gateへ展開する。"""
    available = {"repository", "architecture", "ruff", "format", "docstrings", "mypy"}

    assert expand_selectors(["python-static"], available) == available


def test_scheduler_includes_gate_owned_dependencies() -> None:
    """共有serviceを使うgateは自身が宣言した前提gateを追加する。"""
    available = {"supabase-preflight", "integration", "e2e"}
    gates = [
        Gate("supabase-preflight", "preflight"),
        Gate("e2e", "browser", dependencies=("supabase-preflight",)),
    ]

    assert expand_selectors(["e2e"], available) == {"e2e"}
    assert [[gate.name for gate in stage] for stage in select_stages([gates], ["e2e"])] == [
        ["supabase-preflight"],
        ["e2e"],
    ]


def test_scheduler_places_dependencies_in_an_earlier_stage() -> None:
    """依存gateだけを先行stageへ分離する。"""
    gates = [
        Gate("supabase-preflight", "preflight", cwd=Path(".")),
        Gate(
            "e2e",
            "browser",
            cwd=Path("."),
            dependencies=("supabase-preflight",),
        ),
    ]

    stages = select_stages([gates], ["e2e"])

    assert [[gate.name for gate in stage] for stage in stages] == [
        ["supabase-preflight"],
        ["e2e"],
    ]


def test_unknown_gate_is_rejected() -> None:
    """入力ミスを空の成功として扱わない。"""
    with pytest.raises(ValueError, match="未定義"):
        expand_selectors(["unknown"], {"ruff"})


def test_scheduler_serializes_only_shared_exclusive_resources() -> None:
    """同じ排他resourceを使うgateだけを別stageへ分離する。"""
    gates = [
        Gate("service-a", "integration", exclusive_resources=("supabase",)),
        Gate("service-b", "browser", exclusive_resources=("supabase", "browser")),
        Gate("container", "container", exclusive_resources=("docker",)),
    ]

    stages = select_stages([gates], ["service-a", "service-b", "container"])

    assert [[gate.name for gate in stage] for stage in stages] == [
        ["container", "service-a"],
        ["service-b"],
    ]


def test_deep_domain_and_service_tests_have_independent_prerequisites() -> None:
    """local DB不足時も外部serviceへ依存しないdeep testを実行できる。"""
    gates = {gate.name: gate for stage in _profile_stages("deep", jobs=1) for gate in stage}

    assert gates["deep-tests"].dependencies == ()
    assert "deep" in gates["deep-tests"].command
    assert gates["deep-integration"].dependencies == ()
    assert gates["deep-integration"].exclusive_resources == ()
    assert "deep and not supabase" in gates["deep-integration"].command
    assert gates["deep-supabase"].dependencies == ("supabase-preflight",)
    assert gates["deep-supabase"].exclusive_resources == ("supabase",)
    assert "deep and supabase" in gates["deep-supabase"].command
