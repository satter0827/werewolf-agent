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
from scripts.quality.models import Gate, ResourceLease, RunContext
from scripts.supabase.preflight import isolated_project_id, prepare_supabase

GATES = ("supabase-preflight", "supabase-integration")


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
            "supabase-integration",
            "Supabase code integration",
            (
                sys.executable,
                "-m",
                "pytest",
                "--test-level=release",
                "-m",
                "supabase and not deep",
                "-n",
                "0",
                "--junitxml",
                str(run_dir / "test-results" / "supabase-integration.xml"),
                "--json-report",
                "--json-report-file",
                str(run_dir / "test-results" / "supabase-integration.json"),
                "--html",
                str(run_dir / "test-results" / "supabase-integration.html"),
                "--self-contained-html",
                "tests/integration/supabase",
            ),
            dependencies=("supabase-preflight",),
            exclusive_resources=("supabase",),
            artifacts=(
                "test-results/supabase-integration.xml",
                "test-results/supabase-integration.json",
                "test-results/supabase-integration.html",
            ),
        ),
    ]


def start_supabase(context: RunContext, _: Path) -> CommandResult:
    """品質run専用Supabaseを準備して所有情報を記録する。"""
    started = time.monotonic()
    isolated_root = LAYOUT.runtime / "supabase" / context.run_id
    lease = context.resources.setdefault("supabase", ResourceLease("supabase"))
    lease.cleanup_required = True
    lease.workdir = isolated_root
    lease.identifier = isolated_project_id(isolated_root)
    try:
        preflight = prepare_supabase(
            timeout_seconds=min(context.timeout_seconds, 180),
            isolated_root=isolated_root,
            base_environment=context.environment,
        )
    except EnvironmentBlockedError:
        if isolated_root.exists():
            remove_managed_path(isolated_root)
        lease.cleanup_required = False
        lease.workdir = None
        lease.identifier = None
        raise
    lease.environment = preflight.environment
    lease.cleanup_required = preflight.workdir is not None
    lease.workdir = preflight.workdir
    lease.identifier = preflight.project_id
    context.environment.update(lease.environment)
    return CommandResult(
        ["python", "-m", "scripts.supabase", "preflight"],
        0,
        time.monotonic() - started,
        "ローカルSupabaseの準備が完了しました。\n",
    )


def stop_supabase(context: RunContext, _: Path) -> CommandResult:
    """品質用Supabaseと一時projectを停止・削除する。"""
    started = time.monotonic()
    lease = context.resources.get("supabase", ResourceLease("supabase"))
    command = ["supabase", "stop", "--no-backup"]
    if lease.identifier is not None:
        command.extend(["--project-id", lease.identifier])
    if lease.workdir is not None:
        command.extend(["--workdir", str(lease.workdir)])
        if not lease.workdir.exists():
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
        if result.returncode == 0 and lease.workdir is not None and lease.workdir.exists():
            remove_managed_path(lease.workdir)
    finally:
        supabase_home = context.environment.get("SUPABASE_HOME")
        if supabase_home:
            profile = Path(supabase_home)
            if profile.exists():
                remove_temporary_path(profile)
        lease.cleanup_required = False
    return CommandResult(
        command,
        result.returncode,
        time.monotonic() - started,
        result.output,
        result.timed_out,
    )


__all__ = ["GATES", "build", "start_supabase", "stop_supabase"]
