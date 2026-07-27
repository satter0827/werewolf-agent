"""CIとcontainer構成が品質runnerの公開契約に従うことを検査する。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_quality_workflow_keeps_pr_main_and_manual_coverage() -> None:
    """PR、main、手動実行へ適切なprofileを割り当てる。"""
    workflow = _read(".github/workflows/quality.yml")

    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "python -m scripts.quality check" in workflow
    assert "python -m scripts.quality release" in workflow
    assert "python -m scripts.quality deep --confirm-deep" in workflow


def test_quality_workflow_uses_the_repository_environment_command() -> None:
    """取得を伴う準備をrepository内のenvironment commandへ分離する。"""
    workflow = _read(".github/workflows/quality.yml")

    for command in (
        "python -m scripts.environment setup focus",
        "python -m scripts.environment setup check",
        "python -m scripts.environment setup release",
        "python -m scripts.environment setup deep",
    ):
        assert command in workflow
    assert "python -m scripts.quality focus --fresh" in workflow
    assert "--pull=false" not in workflow
    assert "supabase stop --no-backup" not in workflow
    assert ".werewolf-agent/operations" in workflow


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
    assert "--browser.gatherUsageStats=false" in compose
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
