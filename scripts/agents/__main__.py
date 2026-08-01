"""Agent moduleの安定性と分析用証拠を明示実行する。"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from scripts.agents.review import preflight, resolve_run, run_suite, write_comparison
from scripts.agents.ui import run_local_ui


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight")
    run = subparsers.add_parser("run")
    run.add_argument("--provider", choices=("fake", "local", "openai"), default="local")
    run.add_argument("--suite", choices=("smoke", "full-game", "standard"), default="smoke")
    run.add_argument("--seed", type=int, default=7)
    run.add_argument(
        "--deliberation-level",
        choices=("quick", "standard", "deep"),
        default="standard",
    )
    run.add_argument("--confirm-paid", action="store_true")
    run.add_argument("--preset", action="append", default=[])
    compare = subparsers.add_parser("compare")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--candidate", required=True)
    subparsers.add_parser("local-ui")
    arguments = parser.parse_args(argv)

    if arguments.command == "preflight":
        state, evidence = preflight()
        print(json.dumps({"state": state, **evidence}, ensure_ascii=False, indent=2))
        return _exit_code(state)
    if arguments.command == "run":
        state, run_dir = run_suite(
            arguments.provider,
            arguments.suite,
            confirm_paid=arguments.confirm_paid,
            seed=arguments.seed,
            deliberation_level=arguments.deliberation_level,
            selected_presets=arguments.preset,
        )
        print(f"state: {state}")
        print(f"review artifacts: {run_dir}")
        return _exit_code(state)
    if arguments.command == "compare":
        baseline = resolve_run(arguments.baseline)
        candidate = resolve_run(arguments.candidate)
        json_path, markdown_path = write_comparison(baseline, candidate)
        print(f"comparison: {json_path}")
        print(f"summary: {markdown_path}")
        return 0
    state, run_dir = run_local_ui()
    print(f"state: {state}")
    print(f"review artifacts: {run_dir}")
    return _exit_code(state)


def _exit_code(state: str) -> int:
    if state == "passed":
        return 0
    if state in {"degraded", "failed"}:
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
