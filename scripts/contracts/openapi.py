"""TypeScript client生成に使用するFastAPI contractを出力する。"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from werewolf_agent.api.bootstrap import create_app


def build_parser() -> argparse.ArgumentParser:
    """出力先を選択できるCLI parserを返す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "contracts" / "openapi.json",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Write deterministic OpenAPI JSON at the repository root."""
    target = build_parser().parse_args(argv).output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(create_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
