"""Python静的検査gate。"""

import sys

from scripts._infra.process import TEMPORARY_ROOT
from scripts.quality.models import Gate

GATES = ("ruff", "format", "docstrings", "mypy")


def build() -> list[Gate]:
    """各toolの正本設定を呼ぶPython静的gateを返す。"""
    python = sys.executable
    return [
        Gate("ruff", "Python lint", (python, "-m", "ruff", "check", "--no-cache", ".")),
        Gate(
            "format",
            "Python format",
            (python, "-m", "ruff", "format", "--check", "--no-cache", "."),
        ),
        Gate(
            "docstrings",
            "Google style docstring",
            (
                python,
                "-m",
                "ruff",
                "check",
                "--no-cache",
                "--select",
                "D",
                "src/werewolf_agent",
            ),
        ),
        Gate(
            "mypy",
            "Python type check",
            (
                python,
                "-m",
                "mypy",
                "--no-incremental",
                "--cache-dir",
                str(TEMPORARY_ROOT / "mypy"),
                "src",
                "scripts",
            ),
        ),
    ]


__all__ = ["GATES", "build"]
