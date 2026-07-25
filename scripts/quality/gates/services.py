"""Supabase integration gate。"""

import sys
import time
from pathlib import Path

from scripts._infra.artifacts import LAYOUT
from scripts._infra.process import (
    CommandResult,
    EnvironmentBlockedError,
    remove_managed_path,
    remove_temporary_path,
    run_command,
)
from scripts.quality.models import Gate, RunContext
from scripts.supabase.preflight import isolated_project_id, prepare_supabase

GATES = ("supabase-preflight", "integration")


def build(run_dir: Path) -> list[Gate]:
    """Supabaseの前提確認とintegration test gateを返す。"""
    return [
        Gate(
            "supabase-preflight",
            "Local Supabase preflight",
            (sys.executable, "-m", "scripts.supabase", "preflight"),
            action=start_supabase,
            exclusive_resources=("supabase",),
        ),
        Gate(
            "integration",
            "Package, Supabase and Streamlit integration",
            (
                sys.executable,
                "-m",
                "pytest",
                "--test-level=release",
                "-m",
                "not deep",
                "-n",
                "0",
                "--junitxml",
                str(run_dir / "test-results" / "integration.xml"),
                "tests/integration",
            ),
            dependencies=("supabase-preflight",),
            exclusive_resources=("supabase",),
            artifacts=("test-results/integration.xml",),
        ),
    ]


def start_supabase(context: RunContext, _: Path) -> CommandResult:
    """品質run専用Supabaseを準備して所有情報を記録する。"""
    started = time.monotonic()
    isolated_root = LAYOUT.runtime / "supabase" / context.run_id
    context.supabase_cleanup_required = True
    context.supabase_workdir = isolated_root
    context.supabase_project_id = isolated_project_id(isolated_root)
    try:
        preflight = prepare_supabase(
            timeout_seconds=min(context.timeout_seconds, 180),
            isolated_root=isolated_root,
            base_environment=context.environment,
        )
    except EnvironmentBlockedError:
        if isolated_root.exists():
            remove_managed_path(isolated_root)
        context.supabase_cleanup_required = False
        context.supabase_workdir = None
        context.supabase_project_id = None
        raise
    context.supabase_environment = preflight.environment
    context.supabase_cleanup_required = preflight.workdir is not None
    context.supabase_workdir = preflight.workdir
    context.supabase_project_id = preflight.project_id
    context.environment.update(context.supabase_environment)
    return CommandResult(
        ["python", "-m", "scripts.supabase", "preflight"],
        0,
        time.monotonic() - started,
        "ローカルSupabaseの準備が完了しました。\n",
    )


def stop_supabase(context: RunContext, _: Path) -> CommandResult:
    """品質用Supabaseと一時projectを停止・削除する。"""
    started = time.monotonic()
    command = ["supabase", "stop", "--no-backup"]
    if context.supabase_project_id is not None:
        command.extend(["--project-id", context.supabase_project_id])
    if context.supabase_workdir is not None:
        command.extend(["--workdir", str(context.supabase_workdir)])
        if not context.supabase_workdir.exists():
            result = CommandResult(
                command,
                0,
                time.monotonic() - started,
                "品質用Supabaseは既に停止・削除されています。\n",
            )
        else:
            result = run_command(command, timeout_seconds=60, environment=context.environment)
    else:
        result = run_command(command, timeout_seconds=60, environment=context.environment)
    try:
        if (
            result.returncode == 0
            and context.supabase_workdir is not None
            and context.supabase_workdir.exists()
        ):
            remove_managed_path(context.supabase_workdir)
    finally:
        supabase_home = context.environment.get("SUPABASE_HOME")
        if supabase_home:
            profile = Path(supabase_home)
            if profile.exists():
                remove_temporary_path(profile)
    return CommandResult(
        command,
        result.returncode,
        time.monotonic() - started,
        result.output,
        result.timed_out,
    )


__all__ = ["GATES", "build", "start_supabase", "stop_supabase"]
