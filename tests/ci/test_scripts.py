from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def test_scripts_directory_keeps_only_executable_script_formats() -> None:
    paths = [path for path in SCRIPTS.iterdir() if path.is_file()]

    assert paths
    for path in paths:
        if path.name == "README.md":
            continue
        assert path.suffix in {".cmd", ".ps1", ".py"}


def test_expected_batch_scripts_exist() -> None:
    for name in (
        "run-cli.cmd",
        "run-streamlit.cmd",
        "run-worker.cmd",
        "preflight-supabase.cmd",
        "check-all.cmd",
        "rebuild-sphinx-docs.cmd",
        "clean-caches.cmd",
    ):
        assert (SCRIPTS / name).is_file()
    assert (SCRIPTS / "run-e2e.ps1").is_file()
    assert (SCRIPTS / "apply_migrations.py").is_file()
    assert (SCRIPTS / "export_openapi.py").is_file()


def test_clean_caches_keeps_persistent_artifacts_out_of_remove_targets() -> None:
    script = _read("scripts/clean-caches.cmd")

    assert 'call :clean_path ".werewolf-agent\\cache\\uv"' not in script
    assert 'call :clean_path ".werewolf-agent\\db"' not in script
    assert 'call :clean_path ".werewolf-agent\\logs"' not in script
    assert 'call :clean_path ".werewolf-agent\\cache\\pytest"' in script
    assert 'call :clean_path ".werewolf-agent\\cache\\sphinx"' in script
    assert 'call :clean_path "docs\\sphinx\\_build"' in script


def test_sdist_exposes_only_python_build_inputs() -> None:
    pyproject = _read("pyproject.toml")
    sdist = pyproject.split("[tool.hatch.build.targets.sdist]", maxsplit=1)[1].split(
        "[tool.pytest.ini_options]",
        maxsplit=1,
    )[0]

    assert '"src",' in sdist
    for private_development_surface in (
        '".env.example",',
        '"docker",',
        '"docs",',
        '"frontend",',
        '"scripts",',
        '"supabase",',
        '"tests",',
    ):
        assert private_development_surface not in sdist


def test_rebuild_sphinx_uses_project_environment_for_autodoc() -> None:
    script = _read("scripts/rebuild-sphinx-docs.cmd")

    assert "uv run --group docs --extra streamlit sphinx-build" in script
    assert "uv run --no-project" not in script


def test_supabase_preflight_bootstraps_local_runtime() -> None:
    script = _read("scripts/preflight-supabase.cmd")

    assert "SUPABASE_TELEMETRY_DISABLED=1" in script
    assert "supabase start" in script
    assert "supabase status -o env" in script
    assert "supabase migration up" in script
    assert "API_URL" in script
    assert "PUBLISHABLE_KEY" in script
    assert "DB_URL" in script
    assert "WEREWOLF_SUPABASE_URL" in script
    assert "WEREWOLF_SUPABASE_PUBLISHABLE_KEY" in script
    assert "VITE_SUPABASE_URL" in script
    assert "VITE_SUPABASE_PUBLISHABLE_KEY" in script
    assert "WEREWOLF_COMPOSE_SUPABASE_DB_DSN" in script
    assert "host.docker.internal" in script


def test_e2e_uses_the_container_database_dsn() -> None:
    script = _read("scripts/run-e2e.ps1")

    assert "WEREWOLF_COMPOSE_SUPABASE_DB_DSN" in script
    assert "$env:WEREWOLF_SUPABASE_DB_DSN =" not in script


@pytest.mark.skipif(os.name != "nt", reason="batch smoke tests run on Windows")
def test_batch_help_and_dry_run_commands_do_not_require_project_build() -> None:
    for command in (
        ["cmd", "/c", "scripts\\check-all.cmd", "--help"],
        ["cmd", "/c", "scripts\\preflight-supabase.cmd", "--help"],
        ["cmd", "/c", "scripts\\run-streamlit.cmd", "--help"],
        ["cmd", "/c", "scripts\\run-worker.cmd", "--help"],
        ["cmd", "/c", "scripts\\clean-caches.cmd", "--dry-run"],
    ):
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr or result.stdout


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")
