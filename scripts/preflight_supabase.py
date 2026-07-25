"""ローカルSupabaseをrelease検証に使える状態へ整える。"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import socket
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts._support import (
    REPOSITORY_ROOT,
    CommandResult,
    EnvironmentBlockedError,
    quality_environment,
    redact,
    remove_managed_path,
    run_command,
)

_ENV_LINE = re.compile(r'^([A-Z][A-Z0-9_]*)="?(.*?)"?$')
_ALLOWED_STATUS_KEYS = frozenset({"ANON_KEY", "API_URL", "DB_URL", "PUBLISHABLE_KEY"})
_SUPPORTED_SUPABASE_CLI_VERSION = "2.104.0"
_REQUIRED_LOCAL_IMAGES = (
    "public.ecr.aws/supabase/gotrue:v2.189.0",
    "public.ecr.aws/supabase/kong:2.8.1",
    "public.ecr.aws/supabase/postgres:17.6.1.132",
    "public.ecr.aws/supabase/postgrest:v14.12",
)


def is_supported_supabase_version(output: str) -> bool:
    """Supabase CLIが品質基盤で固定した版か判定する。"""
    return output.strip() == _SUPPORTED_SUPABASE_CLI_VERSION


def isolated_project_id(isolated_root: Path) -> str:
    """品質用workdirから再現可能で衝突しないproject IDを返す。"""
    identity = hashlib.sha256(str(isolated_root.resolve()).encode()).hexdigest()[:12]
    return f"werewolf-agent-quality-{identity}"


@dataclass(frozen=True, slots=True)
class SupabasePreflight:
    """Supabase事前確認の結果。"""

    environment: dict[str, str]
    started_by_process: bool
    workdir: Path | None = None
    project_id: str | None = None


def parse_status_environment(output: str) -> dict[str, str]:
    """`supabase status -o env`の出力を環境変数へ変換する。"""
    environment: dict[str, str] = {}
    for raw_line in output.splitlines():
        match = _ENV_LINE.fullmatch(raw_line.strip())
        if match:
            environment[match.group(1)] = match.group(2)
    return environment


def select_status_environment(output: str) -> dict[str, str]:
    """品質実行に必要なSupabase接続値だけを返す。"""
    return {
        key: value
        for key, value in parse_status_environment(output).items()
        if key in _ALLOWED_STATUS_KEYS
    }


def prepare_supabase(
    *,
    timeout_seconds: int = 180,
    isolated_root: Path | None = None,
    base_environment: Mapping[str, str] | None = None,
) -> SupabasePreflight:
    """Supabaseを起動してmigrationとアプリ側の事前確認を行う。"""
    for executable in ("docker", "supabase"):
        if shutil.which(executable) is None:
            raise EnvironmentBlockedError(f"{executable} CLIが見つかりません。")

    environment = dict(base_environment) if base_environment is not None else quality_environment()
    version = run_command(
        ["supabase", "--version"],
        timeout_seconds=30,
        environment=environment,
    )
    if version.returncode != 0 or not is_supported_supabase_version(version.output):
        detected = version.output.strip() or "不明"
        raise EnvironmentBlockedError(
            "Supabase CLIの版が一致しません。"
            f"必要: {_SUPPORTED_SUPABASE_CLI_VERSION}、検出: {detected}"
        )
    workdir = None
    project_id = None
    if isolated_root is not None:
        workdir, project_id = _prepare_isolated_project(isolated_root)
    docker = run_command(
        ["docker", "info"],
        timeout_seconds=30,
        environment=environment,
    )
    if docker.returncode != 0:
        raise EnvironmentBlockedError("Docker engineが起動していません。")
    missing_images = [
        image
        for image in _REQUIRED_LOCAL_IMAGES
        if run_command(
            ["docker", "image", "inspect", image],
            timeout_seconds=30,
            environment=environment,
        ).returncode
        != 0
    ]
    if missing_images:
        raise EnvironmentBlockedError(
            "ローカルSupabase imageが不足しています。初回セットアップを実行してください: "
            + ", ".join(missing_images)
        )

    status = run_command(
        _supabase_command(["status", "-o", "env"], workdir),
        timeout_seconds=30,
        environment=environment,
    )
    started_by_process = False
    if status.returncode != 0:
        started = run_command(
            _supabase_command(
                [
                    "start",
                    "--exclude",
                    "analytics,edge-runtime,functions,imgproxy,inbucket,meta,realtime,storage,studio,vector",
                ],
                workdir,
            ),
            timeout_seconds=timeout_seconds,
            environment=environment,
        )
        if started.returncode != 0:
            _stop_isolated_project(workdir, project_id, environment)
            raise EnvironmentBlockedError(
                _failure_message("ローカルSupabaseを起動できませんでした。", started)
            )
        started_by_process = True
        status = run_command(
            _supabase_command(["status", "-o", "env"], workdir),
            timeout_seconds=30,
            environment=environment,
        )
    local_environment = select_status_environment(status.output)
    if not local_environment:
        _stop_isolated_project(workdir, project_id, environment)
        raise EnvironmentBlockedError("Supabaseのローカル接続情報を取得できませんでした。")
    aliases = {
        "API_URL": "WEREWOLF_SUPABASE_URL",
        "PUBLISHABLE_KEY": "WEREWOLF_SUPABASE_PUBLISHABLE_KEY",
        "ANON_KEY": "WEREWOLF_SUPABASE_PUBLISHABLE_KEY",
        "DB_URL": "WEREWOLF_SUPABASE_DB_DSN",
    }
    for source, target in aliases.items():
        if source in local_environment:
            local_environment[target] = local_environment[source]

    child_extra = dict(local_environment)
    if isolated_root is not None:
        profile = isolated_root / "profile"
        child_extra.update(
            {
                "APPDATA": str(profile),
                "LOCALAPPDATA": str(profile),
                "XDG_CONFIG_HOME": str(profile),
            }
        )
    child_environment = quality_environment(extra=child_extra)
    migration = run_command(
        _supabase_command(["migration", "up", "--local"], workdir),
        timeout_seconds=timeout_seconds,
        environment=child_environment,
    )
    if migration.returncode != 0:
        _stop_isolated_project(workdir, project_id, environment)
        raise EnvironmentBlockedError(
            _failure_message("Supabase migrationの適用に失敗しました。", migration)
        )

    command = [sys.executable, "-m", "werewolf_agent", "doctor"]
    checked = run_command(
        command,
        timeout_seconds=60,
        environment=child_environment,
    )
    if checked.returncode != 0:
        _stop_isolated_project(workdir, project_id, environment)
        raise EnvironmentBlockedError(
            _failure_message(
                "アプリケーションの接続事前確認に失敗しました: " + " ".join(command[2:]),
                checked,
            )
        )
    return SupabasePreflight(
        local_environment,
        started_by_process,
        workdir=workdir,
        project_id=project_id,
    )


def _prepare_isolated_project(isolated_root: Path) -> tuple[Path, str]:
    """品質用Supabase projectを固有IDとportで複製する。"""
    if isolated_root.exists():
        remove_managed_path(isolated_root)
    workdir = isolated_root
    source = REPOSITORY_ROOT / "supabase"
    target = workdir / "supabase"
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(".branches", ".temp"),
    )
    project_id = isolated_project_id(isolated_root)
    config_path = target / "config.toml"
    config = config_path.read_text(encoding="utf-8")
    config = re.sub(
        r'^project_id = "[^"]+"$',
        f'project_id = "{project_id}"',
        config,
        count=1,
        flags=re.MULTILINE,
    )
    configured_ports = [int(port) for port in re.findall(r"^port = (\d+)$", config, re.MULTILINE)]
    ports = iter(_available_ports(len(configured_ports), excluded=set(configured_ports)))
    config = re.sub(
        r"^port = \d+$",
        lambda _match: f"port = {next(ports)}",
        config,
        flags=re.MULTILINE,
    )
    config_path.write_text(config, encoding="utf-8")
    return workdir, project_id


def _available_ports(count: int, *, excluded: set[int]) -> list[int]:
    """同時に予約して重複を避けたloopback portを返す。"""
    probes: list[socket.socket] = []
    try:
        while len(probes) < count:
            probe = socket.socket()
            probe.bind(("127.0.0.1", 0))
            if int(probe.getsockname()[1]) in excluded:
                probe.close()
                continue
            probes.append(probe)
        return [int(probe.getsockname()[1]) for probe in probes]
    finally:
        for probe in probes:
            probe.close()


def _supabase_command(arguments: Sequence[str], workdir: Path | None) -> list[str]:
    command = ["supabase", *arguments]
    if workdir is not None:
        command.extend(["--workdir", str(workdir)])
    return command


def _stop_isolated_project(
    workdir: Path | None,
    project_id: str | None,
    environment: dict[str, str],
) -> None:
    if workdir is None or project_id is None:
        return
    stopped = run_command(
        [
            "supabase",
            "stop",
            "--project-id",
            project_id,
            "--no-backup",
            "--workdir",
            str(workdir),
        ],
        timeout_seconds=60,
        environment=environment,
    )
    if stopped.returncode == 0 and workdir.exists():
        remove_managed_path(workdir)


def _failure_message(message: str, result: CommandResult) -> str:
    detail = redact("\n".join(result.output.strip().splitlines()[-20:]))
    return f"{message}\n{detail}" if detail else message


def build_parser() -> argparse.ArgumentParser:
    """コマンドライン引数を構築する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=_positive_int, default=180)
    return parser


def _positive_int(value: str) -> int:
    """1以上の整数をargparse向けに検証する。"""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("1以上の整数を指定してください。")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    """Supabase事前確認を実行する。"""
    arguments = build_parser().parse_args(argv)
    try:
        prepare_supabase(timeout_seconds=arguments.timeout)
    except EnvironmentBlockedError as error:
        print(str(error), file=sys.stderr)
        return 2
    print("ローカルSupabaseの準備が完了しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
