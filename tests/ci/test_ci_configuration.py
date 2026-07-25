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

    assert "docker compose build api worker frontend streamlit test e2e" in workflow
    runtime_build_command = (
        "docker build --target runtime -f docker/backend.Dockerfile "
        "-t werewolf-agent-worker:runtime ."
    )
    assert runtime_build_command in workflow
    assert "docker compose --profile test run --rm --no-deps test" in workflow
    assert "docker compose down -v" in workflow
    for command in (
        "npm ci",
        "npm audit --audit-level=low",
        "npm run generate:api",
        "git diff --exit-code -- src/generated/api.ts",
        "npm test",
        "npm run lint",
        "npm run build",
    ):
        assert command in workflow


def test_backend_dev_image_contains_the_test_suite() -> None:
    dockerfile = _read("docker/backend.Dockerfile")

    dev = dockerfile.split("FROM base AS dev", 1)[1].split("FROM base AS runtime", 1)[0]
    for copied_path in (
        ".github",
        "docker",
        "docs",
        "frontend",
        "tests",
    ):
        assert f"COPY {copied_path}" in dev
    assert "openapi.json" in dev


def test_compose_exposes_isolated_runtime_and_test_services() -> None:
    compose = _read("compose.yaml")

    assert "worker:" in compose
    assert 'profiles: ["dev", "e2e", "production"]' in compose
    assert "command: werewolf-agent-worker run" in compose
    assert 'profiles: ["test"]' in compose
    assert "test:" in compose
    assert "command: pytest" in compose
    test_service = compose.split("\n  test:\n", 1)[1].split("\n  e2e:\n", 1)[0]
    assert "WEREWOLF_SUPABASE_" not in test_service
    assert "OPENAI_API_KEY:" in compose
    worker = compose.split("  worker:", 1)[1].split("  frontend:", 1)[0]
    assert "OPENAI_API_KEY:" in worker
    for service in ("api", "frontend", "streamlit"):
        section = compose.split(f"  {service}:", 1)[1].split("\n  ", 1)[0]
        assert "OPENAI_API_KEY:" not in section


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
