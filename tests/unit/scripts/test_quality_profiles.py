"""品質gate selectorとschedulerの契約。"""

import tomllib
from pathlib import Path

import pytest
from scripts.quality.gates.python import build as build_python_gates
from scripts.quality.impact import decide
from scripts.quality.models import Gate
from scripts.quality.profiles import expand_selectors
from scripts.quality.runner import _profile_stages
from scripts.quality.scheduler import select_stages


def test_meaningful_selector_expands_without_coupling_to_profile() -> None:
    """意味単位を個別gateへ展開する。"""
    available = {
        "repository",
        "version-contract",
        "architecture",
        "ruff",
        "format",
        "docstrings",
        "mypy",
    }

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


def test_check_profile_does_not_run_pytest_and_mypy_concurrently() -> None:
    """Workerを持つpytestとmypyを別stageへ分離する。"""
    stages = _profile_stages("check", jobs=4, fresh=True)

    assert all(not {"pytest", "mypy"}.issubset(gate.name for gate in stage) for stage in stages)


def test_deep_domain_and_service_tests_have_independent_prerequisites() -> None:
    """local DB不足時も外部serviceへ依存しないdeep testを実行できる。"""
    gates = {gate.name: gate for stage in _profile_stages("deep", jobs=1) for gate in stage}

    assert "--test-level=check" in gates["pytest"].command
    assert "--confirm-deep" not in gates["pytest"].command
    assert gates["deep-tests"].dependencies == ()
    assert "--test-level=deep" in gates["deep-tests"].command
    assert "--confirm-deep" in gates["deep-tests"].command
    assert "monkey" in gates["deep-tests"].command
    assert gates["deep-integration"].dependencies == ()
    assert gates["deep-integration"].exclusive_resources == ()
    assert "deep and not supabase" in gates["deep-integration"].command
    assert gates["deep-supabase"].dependencies == ("supabase-preflight",)
    assert gates["deep-supabase"].exclusive_resources == ("supabase",)
    assert "deep and supabase" in gates["deep-supabase"].command
    assert gates["docker"].dependencies == ("environment",)
    assert gates["supabase-preflight"].dependencies == ("environment", "supabase-cleanup")
    assert gates["e2e"].dependencies == ("supabase-preflight",)


def test_profiles_declare_the_required_environment_capability() -> None:
    check = [gate for stage in _profile_stages("check", jobs=1) for gate in stage]
    release = [gate for stage in _profile_stages("release", jobs=1) for gate in stage]

    assert all(gate.environment_target == "python" for gate in check)
    assert any(gate.environment_target == "quality" for gate in release)
    assert next(gate for gate in release if gate.name == "e2e").environment_target == "quality"


def test_document_only_change_selects_document_evidence() -> None:
    decision = decide(("docs/design/verification.md",))

    assert decision.profile == "focus"
    assert decision.selectors == ("docs", "repository")


@pytest.mark.parametrize(
    "path",
    (
        "scripts/README.md",
        "scripts/AGENTS.md",
        "src/werewolf_agent/domain/AGENTS.md",
    ),
)
def test_documentation_guides_select_document_evidence(path: str) -> None:
    """directory固有のguideも文書変更として判定する。"""
    decision = decide((path,))

    assert decision.profile == "focus"
    assert decision.selectors == ("docs", "repository")


def test_unknown_change_escalates_to_check() -> None:
    decision = decide(("new-system/unknown.ext",))

    assert decision.profile == "check"
    assert decision.selectors == ()
    assert "未登録path" in decision.reason


def test_codex_change_explicitly_selects_check() -> None:
    """Codexの実行制御変更を未知path fallbackに依存させない。"""
    decision = decide((".codex/hooks/github_pr_governance.py",))

    assert decision.profile == "check"
    assert decision.selectors == ()
    assert "未登録path" not in decision.reason


def test_python_static_gates_cover_every_configured_source() -> None:
    """静的検査の実行対象と再利用fingerprintを同じsource境界へ揃える。"""
    root = Path(__file__).resolve().parents[3]
    with (root / "pyproject.toml").open("rb") as stream:
        configured = tomllib.load(stream)["tool"]["mypy"]["files"]
    gates = {gate.name: gate for gate in build_python_gates(fresh=True)}

    assert configured == ["src", "scripts", "notebooks/werewolf_demo", ".codex/hooks"]
    assert all(path not in gates["mypy"].command for path in configured)
    for gate_name in ("ruff", "format", "mypy"):
        assert "notebooks/**/*.py" in gates[gate_name].inputs
        assert ".codex/**/*.py" in gates[gate_name].inputs


def test_unknown_change_never_downgrades_a_release_boundary() -> None:
    """未登録pathとの混在で既に選ばれた上位profileを下げない。"""
    decision = decide(
        (
            "scripts/browser/e2e.py",
            "new-system/unknown.ext",
        )
    )

    assert decision.profile == "release"
    assert decision.selectors == ()
    assert "未登録path" in decision.reason


@pytest.mark.parametrize(
    ("path", "profile"),
    [
        ("tests/integration/clients/test_streamlit_app.py", "check"),
        ("tests/integration/supabase/test_store.py", "release"),
        ("scripts/browser/scenarios/test_streamlit.py", "release"),
        ("src/werewolf_agent/clients/streamlit/app.py", "release"),
        (".streamlit/config.toml", "release"),
        ("src/werewolf_agent/api/app.py", "check"),
    ],
)
def test_risk_boundaries_select_the_profile_that_exercises_the_change(
    path: str,
    profile: str,
) -> None:
    """変更したintegration境界を実行しない軽量profileへ割り当てない。"""
    decision = decide((path,))

    assert decision.profile == profile
    assert decision.selectors == ()
