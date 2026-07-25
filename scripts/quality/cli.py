"""品質profileと個別gateのCLI。"""

from __future__ import annotations

from collections.abc import Sequence

from scripts.quality.runner import main as runner_main


def main(argv: Sequence[str] | None = None) -> int:
    """品質CLIを実行する。"""
    return runner_main(argv)


__all__ = ["main"]
