from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_docker_workflow_keeps_pr_and_main_push_coverage() -> None:
    workflow = _read(".github/workflows/docker.yml")

    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "branches:" in workflow
    assert "- main" in workflow


def test_docker_workflow_runs_container_build_and_test() -> None:
    workflow = _read(".github/workflows/docker.yml")

    assert "docker compose build worker test" in workflow
    runtime_build_command = (
        "docker build --target runtime -f docker/backend.Dockerfile "
        "-t werewolf-agent-worker:runtime ."
    )
    assert runtime_build_command in workflow
    assert "docker compose --profile tools run --rm test" in workflow
    assert "docker compose down -v" in workflow


def test_compose_tools_expose_worker_and_pytest_services() -> None:
    compose = _read("compose.yaml")

    assert "worker:" in compose
    assert 'profiles: ["worker"]' in compose
    assert "command: werewolf-agent-worker run" in compose
    assert 'profiles: ["tools"]' in compose
    assert "test:" in compose
    assert "command: pytest" in compose


def test_documented_validation_commands_match_repo_tooling() -> None:
    docs = "\n".join(
        [
            _read("README.md"),
            _read("docs/notes/development.md"),
            _read("AGENTS.md"),
        ]
    )
    pyproject = _read("pyproject.toml")

    for command in (
        "uv run pytest",
        "uv run ruff check .",
        "uv run ruff format --check .",
        ("uv run --no-sync ruff check --no-cache --select D --ignore D100,D104 src/werewolf_agent"),
        "uv run mypy src",
        "supabase migration up",
        "uv run --extra worker werewolf-agent-worker run",
        "uv run werewolf-agent doctor",
        "uv run werewolf-agent play --role-count werewolf=1",
        "docker compose build",
        "docker compose --profile worker up worker",
        "docker compose run --rm test",
    ):
        assert command in docs

    assert "[dependency-groups]" in pyproject
    assert "dev = [" in pyproject
    assert "[project.optional-dependencies]" in pyproject
    assert "worker = [" in pyproject
    assert "streamlit = [" in pyproject
    assert 'testpaths = ["tests"]' in pyproject


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")
