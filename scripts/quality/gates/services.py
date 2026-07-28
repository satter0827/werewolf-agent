"""Supabase integration gate。"""

import sys
import time
from pathlib import Path

from scripts._infra.artifacts import LAYOUT
from scripts._infra.process import (
    CommandResult,
    EnvironmentBlockedError,
    remove_managed_path,
    run_command,
)
from scripts.quality.models import Gate, ResourceLease, RunContext
from scripts.supabase.preflight import isolated_project_id, prepare_supabase

QUALITY_SUPABASE_PREFIX = "werewolf-agent-quality-"
GATES = (
    "supabase-cleanup",
    "supabase-preflight",
    "supabase-lint",
    "supabase-integration",
)


def build(run_dir: Path) -> list[Gate]:
    """Supabaseの前提確認とintegration test gateを返す。"""
    return [
        Gate(
            "supabase-cleanup",
            "Orphaned quality Supabase cleanup",
            (
                "docker",
                "ps",
                "--all",
                "--filter",
                "label=com.supabase.cli.project",
            ),
            action=cleanup_orphaned_supabase,
            exclusive_resources=("supabase",),
        ),
        Gate(
            "supabase-preflight",
            "Local Supabase preflight",
            (sys.executable, "-m", "scripts.supabase", "preflight"),
            action=start_supabase,
            dependencies=("environment", "supabase-cleanup"),
            exclusive_resources=("supabase",),
        ),
        Gate(
            "supabase-lint",
            "Local Supabase schema lint",
            ("supabase", "db", "lint", "--local", "--fail-on", "error"),
            action=lint_supabase,
            dependencies=("supabase-preflight",),
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


def lint_supabase(context: RunContext, _: Path) -> CommandResult:
    """品質runが所有するlocal DBだけをlintする。"""
    lease = context.resources.get("supabase")
    if lease is None or lease.workdir is None:
        raise EnvironmentBlockedError("品質用Supabase workdirを取得できません。")
    return run_command(
        [
            "supabase",
            "db",
            "lint",
            "--local",
            "--fail-on",
            "error",
            "--workdir",
            str(lease.workdir),
        ],
        timeout_seconds=min(context.timeout_seconds, 120),
        environment=context.environment,
    )


def cleanup_orphaned_supabase(context: RunContext, _: Path) -> CommandResult:
    """失敗した過去runが残した品質専用Supabaseを開始前に回収する。"""
    started = time.monotonic()
    discovery_commands = [
        [
            "docker",
            "ps",
            "--all",
            "--filter",
            "label=com.supabase.cli.project",
            "--format",
            '{{.Label "com.supabase.cli.project"}}',
        ],
        [
            "docker",
            "volume",
            "ls",
            "--filter",
            "label=com.supabase.cli.project",
            "--format",
            '{{.Label "com.supabase.cli.project"}}',
        ],
    ]
    discovered_projects: list[str] = []
    for command in discovery_commands:
        discovered = run_command(command, timeout_seconds=30, environment=context.environment)
        if discovered.returncode != 0:
            return discovered
        discovered_projects.extend(discovered.output.splitlines())
    project_ids = sorted(
        {
            line.strip()
            for line in discovered_projects
            if line.strip().startswith(QUALITY_SUPABASE_PREFIX)
        }
    )
    outputs: list[str] = []
    for project_id in project_ids:
        stopped = run_command(
            ["supabase", "stop", "--project-id", project_id, "--no-backup"],
            timeout_seconds=60,
            environment=context.environment,
        )
        outputs.append(stopped.output)
        if stopped.returncode != 0:
            return CommandResult(
                discovery_commands[0],
                stopped.returncode,
                time.monotonic() - started,
                "".join(outputs),
                stopped.timed_out,
            )
    message = (
        f"品質用Supabaseの孤児projectを{len(project_ids)}件回収しました。\n"
        if project_ids
        else "品質用Supabaseの孤児projectはありません。\n"
    )
    return CommandResult(
        discovery_commands[0], 0, time.monotonic() - started, message + "".join(outputs)
    )


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
    if lease.identifier is None or lease.workdir is None:
        lease.cleanup_required = False
        return CommandResult(
            ["supabase", "stop"],
            0,
            time.monotonic() - started,
            "品質用Supabaseの所有resourceはありません。\n",
        )
    command = [
        "supabase",
        "stop",
        "--project-id",
        lease.identifier,
        "--no-backup",
        "--workdir",
        str(lease.workdir),
    ]
    if not lease.workdir.exists():
        result = CommandResult(
            command,
            0,
            time.monotonic() - started,
            "品質用Supabaseは既に停止・削除されています。\n",
        )
    else:
        result = run_command(command, timeout_seconds=60, environment=context.environment)
    cleanup_returncode = result.returncode
    outputs = [result.output]
    if result.returncode == 0 and lease.workdir is not None and lease.workdir.exists():
        try:
            remove_managed_path(lease.workdir)
        except OSError as error:
            cleanup_returncode = 1
            outputs.append(str(error))
    supabase_home = context.environment.get("SUPABASE_HOME")
    if supabase_home:
        profile = Path(supabase_home)
        if profile.exists():
            try:
                remove_managed_path(profile)
            except OSError as error:
                cleanup_returncode = 1
                outputs.append(str(error))
    lease.cleanup_required = cleanup_returncode != 0
    if not lease.cleanup_required:
        lease.identifier = None
        lease.workdir = None
    return CommandResult(
        command,
        cleanup_returncode,
        time.monotonic() - started,
        "\n".join(output for output in outputs if output),
        result.timed_out,
    )


__all__ = [
    "GATES",
    "build",
    "cleanup_orphaned_supabase",
    "lint_supabase",
    "start_supabase",
    "stop_supabase",
]
