"""Supabase開発操作のcommand line入口。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from scripts.supabase.migrations import main as migrations_main
from scripts.supabase.preflight import main as preflight_main


def main(argv: Sequence[str] | None = None) -> int:
    """Supabase subcommandを実行する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "migrate"))
    arguments, remaining = parser.parse_known_args(argv)
    if arguments.command == "preflight":
        return preflight_main(remaining)
    if remaining:
        parser.error("migrateは追加引数を受け付けません。")
    migrations_main()
    return 0


raise SystemExit(main())
