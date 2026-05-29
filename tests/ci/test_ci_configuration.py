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

    assert "docker compose build api" in workflow
    assert (
        "docker build --target runtime -f docker/backend.Dockerfile -t werewolf-agent-api:runtime ."
    ) in workflow
    assert "docker compose --profile tools run --rm test" in workflow
    assert "docker compose down -v" in workflow


def test_compose_tools_expose_migration_and_pytest_services() -> None:
    compose = _read("compose.yaml")

    assert "migrate:" in compose
    assert 'profiles: ["tools"]' in compose
    assert "command: alembic upgrade head" in compose
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
        "uv run mypy backend/src",
        "uv run --extra api alembic upgrade head",
        "uv run werewolf-agent doctor",
        "uv run werewolf-agent play --api-url http://127.0.0.1:8000/api/v1",
        "docker compose build",
        "docker compose run --rm migrate",
        "docker compose run --rm test",
    ):
        assert command in docs

    assert "[dependency-groups]" in pyproject
    assert "dev = [" in pyproject
    assert "[project.optional-dependencies]" in pyproject
    assert "api = [" in pyproject
    assert 'testpaths = ["tests"]' in pyproject


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")
