"""Supabase開発操作のcommand line入口。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from scripts._infra.process import EnvironmentBlockedError
from scripts.supabase.migrations import main as migrations_main
from scripts.supabase.preflight import (
    SupabasePreflight,
    serve_supabase,
    stop_supabase,
)
from scripts.supabase.preflight import (
    main as preflight_main,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Supabase subcommandを実行する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "serve", "stop", "migrate"))
    arguments, remaining = parser.parse_known_args(argv)
    if arguments.command == "preflight":
        return preflight_main(remaining)
    if arguments.command == "serve":
        serve_parser = argparse.ArgumentParser(description="ローカルSupabaseを監督します。")
        serve_parser.add_argument("--timeout", type=int, default=180)
        serve_parser.add_argument("--stop-on-exit", action="store_true")
        serve_arguments = serve_parser.parse_args(remaining)
        if serve_arguments.timeout < 1:
            serve_parser.error("--timeoutは1以上を指定してください。")
        return serve_supabase(
            timeout_seconds=serve_arguments.timeout,
            stop_on_exit=serve_arguments.stop_on_exit,
        )
    if arguments.command == "stop":
        if remaining:
            parser.error("stopは追加引数を受け付けません。")
        try:
            stop_supabase(
                SupabasePreflight(environment={}, started_by_process=False),
                force=True,
            )
        except EnvironmentBlockedError as error:
            print(str(error))
            return 2
        return 0
    if remaining:
        parser.error("migrateは追加引数を受け付けません。")
    migrations_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
