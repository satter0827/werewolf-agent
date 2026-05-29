from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def test_scripts_directory_keeps_executable_code_batch_only() -> None:
    paths = [path for path in SCRIPTS.iterdir() if path.is_file()]

    assert paths
    for path in paths:
        if path.name == "README.md":
            continue
        assert path.suffix == ".cmd"


def test_expected_batch_scripts_exist() -> None:
    for name in (
        "run-cli.cmd",
        "run-api.cmd",
        "check-all.cmd",
        "rebuild-sphinx-docs.cmd",
        "clean-caches.cmd",
    ):
        assert (SCRIPTS / name).is_file()


def test_clean_caches_keeps_persistent_artifacts_out_of_remove_targets() -> None:
    script = _read("scripts/clean-caches.cmd")

    assert 'call :clean_path ".werewolf-agent\\cache\\uv"' not in script
    assert 'call :clean_path ".werewolf-agent\\db"' not in script
    assert 'call :clean_path ".werewolf-agent\\logs"' not in script
    assert 'call :clean_path ".werewolf-agent\\cache\\pytest"' in script
    assert 'call :clean_path ".werewolf-agent\\cache\\sphinx"' in script
    assert 'call :clean_path "docs\\sphinx\\_build"' in script


def test_sdist_includes_scripts() -> None:
    pyproject = _read("pyproject.toml")

    assert '"scripts",' in pyproject


@pytest.mark.skipif(os.name != "nt", reason="batch smoke tests run on Windows")
def test_batch_help_and_dry_run_commands_do_not_require_project_build() -> None:
    for command in (
        ["cmd", "/c", "scripts\\check-all.cmd", "--help"],
        ["cmd", "/c", "scripts\\run-api.cmd", "--help"],
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
