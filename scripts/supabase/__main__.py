"""Supabase開発操作のcommand line入口。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Supabase subcommandを実行する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "reserve", "serve", "wait", "migrate"))
    arguments, remaining = parser.parse_known_args(argv)
    if arguments.command == "preflight":
        from scripts.supabase.preflight import main as preflight_main

        return preflight_main(remaining)
    if arguments.command == "reserve":
        from scripts.supabase.preflight import reserve_development_session

        reserve_parser = argparse.ArgumentParser(description="開発セッションを予約します。")
        reserve_parser.add_argument(
            "session",
            choices=("full-stack", "backend", "api", "worker"),
        )
        reserve_arguments = reserve_parser.parse_args(remaining)
        return reserve_development_session(reserve_arguments.session)
    if arguments.command == "serve":
        from scripts.supabase.preflight import serve_supabase

        serve_parser = argparse.ArgumentParser(description="ローカルSupabaseを監督します。")
        serve_parser.add_argument("--timeout", type=int, default=180)
        serve_parser.add_argument("--stop-on-exit", action="store_true")
        serve_parser.add_argument("--reserved", action="store_true")
        serve_arguments = serve_parser.parse_args(remaining)
        if serve_arguments.timeout < 1:
            serve_parser.error("--timeoutは1以上を指定してください。")
        return serve_supabase(
            timeout_seconds=serve_arguments.timeout,
            stop_on_exit=serve_arguments.stop_on_exit,
            reserved=serve_arguments.reserved,
        )
    if arguments.command == "wait":
        from scripts.supabase.preflight import wait_for_supervisor

        wait_parser = argparse.ArgumentParser(description="Supabase supervisorを待機します。")
        wait_parser.add_argument("--timeout", type=int, default=180)
        wait_arguments = wait_parser.parse_args(remaining)
        if wait_arguments.timeout < 1:
            wait_parser.error("--timeoutは1以上を指定してください。")
        return wait_for_supervisor(timeout_seconds=wait_arguments.timeout)
    if remaining:
        parser.error("migrateは追加引数を受け付けません。")
    from scripts.supabase.migrations import main as migrations_main

    migrations_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
