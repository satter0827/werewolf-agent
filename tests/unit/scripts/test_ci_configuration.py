"""CIとcontainer構成が品質runnerの公開契約に従うことを検査する。"""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_quality_workflow_separates_develope_and_main_boundaries() -> None:
    """日常統合はCheck、main境界はDeepと互換性を要求する。"""
    workflow = _read(".github/workflows/quality.yml")

    assert "pull_request:" in workflow
    assert "      - develope" in workflow
    assert "      - main" in workflow
    assert "push:" not in workflow
    assert 'cron: "0 18 * * 0"' in workflow
    assert "workflow_dispatch:" in workflow
    assert "name: Develope / Check" in workflow
    assert "name: Main / Source Branch" in workflow
    assert "name: Main / Readiness" in workflow
    assert "name: Main / Compatibility" in workflow
    assert "python -m scripts.quality check" in workflow
    assert "python -m scripts.quality release" not in workflow
    assert "python -m scripts.quality deep" in workflow
    assert "--confirm-deep" in workflow
    assert "--base-ref origin/develope" in workflow
    assert "--base-ref origin/main" in workflow
    assert "--head-ref ${{ github.event.pull_request.head.sha || 'HEAD' }}" in workflow
    assert "fetch-depth: 0" in workflow


def test_manual_check_reuses_the_develope_pr_job() -> None:
    """選択branchをPR前に同じLinux Checkで検証する。"""
    workflow = _read(".github/workflows/quality.yml")
    develope_check = workflow.split("\n  develope-check:\n", 1)[1].split("\n  main-source:\n", 1)[0]
    scheduled_deep = workflow.split("\n  scheduled-deep:\n", 1)[1]

    assert "github.event_name == 'workflow_dispatch'" in develope_check
    assert "github.base_ref == 'develope'" in develope_check
    assert "--head-ref ${{ github.event.pull_request.head.sha || 'HEAD' }}" in develope_check
    assert "github.event_name == 'schedule'" in scheduled_deep
    assert "workflow_dispatch" not in scheduled_deep


def test_quality_workflow_pins_the_runner_os_generation() -> None:
    """hosted runnerのOS世代をjob間で統一する。"""
    workflow = _read(".github/workflows/quality.yml")
    runners = re.findall(r"^\s+runs-on:\s+([^\s]+)$", workflow, re.MULTILINE)

    assert runners
    assert set(runners) == {"ubuntu-24.04"}


def test_quality_workflow_uses_the_repository_environment_command() -> None:
    """取得を伴う準備をrepository内のenvironment commandへ分離する。"""
    workflow = _read(".github/workflows/quality.yml")

    for command in (
        "python -m scripts.environment setup python",
        "python -m scripts.environment setup quality",
    ):
        assert command in workflow
    assert "python -m scripts.environment setup focus" not in workflow
    assert "python -m scripts.environment setup check" not in workflow
    assert "python -m scripts.environment setup deep" not in workflow
    assert "python -m scripts.quality focus" in workflow
    assert "--pull=false" not in workflow
    assert "supabase stop --no-backup" not in workflow
    assert ".werewolf-agent/operations" in workflow


def test_workflow_actions_are_pinned_and_dependabot_targets_develope() -> None:
    """必須CIの実装をmutable tagへ依存させない。"""
    workflow = _read(".github/workflows/quality.yml")
    actions = re.findall(r"uses:\s+[^@\s]+@([^\s]+)", workflow)

    assert actions
    assert all(re.fullmatch(r"[0-9a-f]{40}", revision) for revision in actions)
    dependabot = _read(".github/dependabot.yml")
    assert "package-ecosystem: github-actions" in dependabot
    assert "target-branch: develope" in dependabot


def test_workflow_javascript_actions_use_node24_releases() -> None:
    """GitHub runnerが廃止済みNode runtimeを強制置換しない。"""
    workflow = _read(".github/workflows/quality.yml")
    expected = {
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9",
        "supabase/setup-cli@46f7f98c7f948ad727d22c1e67fab04c223a0520",
    }

    assert all(action in workflow for action in expected)


def test_main_compatibility_matches_supported_python_versions() -> None:
    """primary Python以外の対応版をmain互換性matrixへ含める。"""
    workflow = _read(".github/workflows/quality.yml")
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    supported = {
        classifier.rsplit("::", maxsplit=1)[-1].strip()
        for classifier in project["classifiers"]
        if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", classifier)
    }

    assert supported == {"3.11", "3.12", "3.13", "3.14"}
    for version in supported - {"3.12"}:
        assert f'"{version}"' in workflow


def test_rulesets_require_the_stable_workflow_checks() -> None:
    """version管理したrulesetとworkflowの必須check名を一致させる。"""
    workflow = _read(".github/workflows/quality.yml")
    expected = {
        "develope.json": {"Develope / Check"},
        "main.json": {"Main / Source Branch", "Main / Readiness", "Main / Compatibility"},
    }
    for filename, contexts in expected.items():
        document = json.loads(_read(f".github/rulesets/{filename}"))
        status_rule = next(
            rule for rule in document["rules"] if rule["type"] == "required_status_checks"
        )
        actual = {item["context"] for item in status_rule["parameters"]["required_status_checks"]}
        assert actual == contexts
        assert all(f"name: {context}" in workflow for context in contexts)
        pull_request_rule = next(
            rule for rule in document["rules"] if rule["type"] == "pull_request"
        )
        assert pull_request_rule["parameters"]["allowed_merge_methods"] == ["merge"]


def test_backend_dev_image_contains_the_test_suite() -> None:
    """container test用stageへ検証対象を含める。"""
    dockerfile = _read("docker/backend.Dockerfile")

    dev = dockerfile.split("FROM dev-dependencies AS dev", 1)[1].split(
        "FROM runtime-dependencies AS runtime", 1
    )[0]
    for copied_path in (".github", "docker", "docs", "tests"):
        assert f"COPY {copied_path}" in dev
    assert "contracts/openapi.json" in dev


def test_compose_exposes_isolated_runtime_and_test_services() -> None:
    """品質対象serviceと秘密情報の境界を維持する。"""
    compose = _read("compose.yaml")

    assert "worker:" in compose
    assert 'profiles: ["dev", "e2e", "production"]' in compose
    assert "command: werewolf-agent-worker run" in compose
    assert 'profiles: ["test"]' in compose
    assert "test:" in compose
    assert "command: pytest" in compose
    streamlit_config = _read(".streamlit/config.toml")
    assert "gatherUsageStats = false" in streamlit_config
    assert "--browser.gatherUsageStats" not in compose
    assert "WEREWOLF_LOG_OUTPUT: ${WEREWOLF_LOG_OUTPUT:-stdout}" in compose
    test_service = compose.split("\n  test:\n", 1)[1].split("\n  e2e:\n", 1)[0]
    assert "WEREWOLF_SUPABASE_" not in test_service
    worker = compose.split("  worker:", 1)[1].split("  streamlit:", 1)[0]
    assert "OPENAI_API_KEY:" in worker
    for service in ("api", "streamlit"):
        section = compose.split(f"  {service}:", 1)[1].split("\n  ", 1)[0]
        assert "OPENAI_API_KEY:" not in section


def test_documented_validation_commands_match_repo_tooling() -> None:
    """利用者向け文書から共通runnerへ到達できる。"""
    docs = "\n".join(
        [
            _read("README.md"),
            _read("docs/design/verification.md"),
            _read("scripts/README.md"),
            _read("AGENTS.md"),
        ]
    )
    pyproject = _read("pyproject.toml")

    for command in (
        "python -m scripts.quality auto",
        "python -m scripts.quality focus",
        "python -m scripts.quality check",
        "python -m scripts.quality release",
        "python -m scripts.quality deep --confirm-deep",
        "python -m scripts.quality clean",
    ):
        assert command in docs
    assert "[tool.werewolf-quality]" in pyproject
    assert 'testpaths = ["tests"]' in pyproject


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")
