"""診断viewのcommand line入口。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from scripts.diagnostics.collector import collect


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("collect",))
    arguments = parser.parse_args(argv)
    if arguments.command == "collect":
        report = collect()
        print(f"診断report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
