"""Python静的検査gate。"""

import sys

from scripts._infra.process import TEMPORARY_ROOT
from scripts.quality.models import CPU_INTENSIVE_RESOURCE, Gate

GATES = ("ruff", "format", "docstrings", "bandit", "secrets", "mypy")


def build(*, fresh: bool = False) -> list[Gate]:
    """各toolの正本設定を呼ぶPython静的gateを返す。"""
    python = sys.executable
    ruff_cache = ("--no-cache",) if fresh else ()
    mypy_cache = ("--no-incremental",) if fresh else ()
    return [
        Gate(
            "ruff",
            "Python lint",
            (python, "-m", "ruff", "check", *ruff_cache, "."),
            inputs=(
                "src/**/*.py",
                "scripts/**/*.py",
                "tests/**/*.py",
                "notebooks/**/*.py",
                ".codex/**/*.py",
                "pyproject.toml",
            ),
            reusable=True,
        ),
        Gate(
            "format",
            "Python format",
            (python, "-m", "ruff", "format", "--check", *ruff_cache, "."),
            inputs=(
                "src/**/*.py",
                "scripts/**/*.py",
                "tests/**/*.py",
                "notebooks/**/*.py",
                ".codex/**/*.py",
                "pyproject.toml",
            ),
            reusable=True,
        ),
        Gate(
            "docstrings",
            "Google style docstring",
            (
                python,
                "-m",
                "ruff",
                "check",
                *ruff_cache,
                "--select",
                "D",
                "src/werewolf_agent",
            ),
            inputs=("src/**/*.py", "pyproject.toml"),
            reusable=True,
        ),
        Gate(
            "bandit",
            "Python security lint",
            (python, "-m", "bandit", "-r", "-q", "-ll", "src/werewolf_agent"),
            inputs=("src/**/*.py", "pyproject.toml", "uv.lock"),
            reusable=True,
        ),
        Gate(
            "secrets",
            "Credential leak scan",
            (python, "-m", "scripts.security", "secrets"),
        ),
        Gate(
            "mypy",
            "Python type check",
            (
                python,
                "-m",
                "mypy",
                *mypy_cache,
                "--cache-dir",
                str(TEMPORARY_ROOT / "mypy"),
            ),
            exclusive_resources=(CPU_INTENSIVE_RESOURCE,),
            inputs=(
                "src/**/*.py",
                "scripts/**/*.py",
                "notebooks/**/*.py",
                ".codex/**/*.py",
                "pyproject.toml",
                "uv.lock",
            ),
            reusable=True,
        ),
    ]


__all__ = ["GATES", "build"]
