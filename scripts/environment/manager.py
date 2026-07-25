"""Lock fileに従って必要な開発依存だけを準備する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from scripts._infra.process import (
    ARTIFACT_ROOT,
    QUALITY_COMPOSE_PROJECT_NAME,
    REPOSITORY_ROOT,
)
from scripts.supabase.constants import LOCAL_EXCLUDED_SERVICES_CSV

STATE_ROOT = ARTIFACT_ROOT / "runtime" / "environment"
PROFILES = ("quick", "check", "release", "deep")
PYTHON_INPUTS = ("pyproject.toml", "uv.lock")
FRONTEND_INPUTS = ("frontend/package.json", "frontend/package-lock.json")
RELEASE_INPUTS = (
    "compose.yaml",
    "docker",
    "frontend",
    "scripts",
    "src",
    "supabase",
)


def _run(
    command: Sequence[str],
    *,
    cwd: Path = REPOSITORY_ROOT,
    quiet: bool = False,
) -> None:
    """準備commandを実行し、秘密値を含み得る出力だけ捕捉する。"""
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=quiet,
        text=quiet,
        encoding="utf-8" if quiet else None,
        errors="replace" if quiet else None,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"環境準備に失敗しました: {' '.join(command)}")


def _version(command: Sequence[str]) -> str:
    executable = shutil.which(command[0]) or command[0]
    completed = subprocess.run(
        [executable, *command[1:]],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unavailable"


def _fingerprint(profile: str) -> str:
    digest = hashlib.sha256()
    inputs = [REPOSITORY_ROOT / relative for relative in (*PYTHON_INPUTS, *FRONTEND_INPUTS)]
    if profile in {"release", "deep"}:
        for relative in RELEASE_INPUTS:
            path = REPOSITORY_ROOT / relative
            inputs.extend(
                candidate
                for candidate in ([path] if path.is_file() else path.rglob("*"))
                if candidate.is_file()
                and not {"__pycache__", "dist", "node_modules"}.intersection(candidate.parts)
            )
    for path in sorted(set(inputs)):
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        digest.update(relative.encode())
        digest.update(path.read_bytes())
    for value in (
        profile,
        _version(("uv", "--version")),
        _version(("node", "--version")),
        _version(("npm", "--version")),
        _version(("docker", "--version")) if profile in {"release", "deep"} else "",
        _version(("supabase", "--version")) if profile in {"release", "deep"} else "",
    ):
        digest.update(value.encode())
    return digest.hexdigest()


def _state_path(profile: str) -> Path:
    return STATE_ROOT / f"{profile}.json"


def _ready(profile: str, fingerprint: str) -> bool:
    state_path = _state_path(profile)
    if not (REPOSITORY_ROOT / ".venv").is_dir():
        return False
    if not (REPOSITORY_ROOT / "frontend" / "node_modules").is_dir():
        return False
    if not state_path.is_file():
        return False
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(state, dict) and state == {
        "fingerprint": fingerprint,
        "profile": profile,
    }


def setup(profile: str = "check") -> None:
    """指定profileに必要な依存をlockに従って準備する。"""
    uv = shutil.which("uv") or "uv"
    npm = shutil.which("npm") or "npm"
    _run((uv, "sync", "--frozen", "--all-groups", "--all-extras"))
    _run((npm, "ci", "--ignore-scripts"), cwd=REPOSITORY_ROOT / "frontend")
    if profile in {"release", "deep"}:
        docker = shutil.which("docker")
        supabase = shutil.which("supabase")
        if docker is None:
            raise RuntimeError("releaseにはDockerが必要です。")
        if supabase is None:
            raise RuntimeError("releaseにはSupabase CLIが必要です。")
        _run(
            (
                supabase,
                "start",
                "--exclude",
                LOCAL_EXCLUDED_SERVICES_CSV,
            ),
            quiet=True,
        )
        _run((supabase, "stop", "--no-backup"), quiet=True)
        _run(
            (
                docker,
                "compose",
                "--project-name",
                QUALITY_COMPOSE_PROJECT_NAME,
                "--profile",
                "e2e",
                "build",
                "api",
                "worker",
                "frontend",
                "frontend-e2e",
                "streamlit",
                "e2e",
                "migrate",
            )
        )
        _run(
            (
                docker,
                "build",
                "--target",
                "runtime",
                "-f",
                "docker/backend.Dockerfile",
                "-t",
                "werewolf-agent-quality-runtime:latest",
                ".",
            )
        )
    fingerprint = _fingerprint(profile)
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    _state_path(profile).write_text(
        json.dumps(
            {"fingerprint": fingerprint, "profile": profile},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def ensure(profile: str = "check") -> bool:
    """不足またはlock変更時だけ指定profileの依存を準備する。"""
    fingerprint = _fingerprint(profile)
    if _ready(profile, fingerprint):
        return False
    setup(profile)
    return True


def build_parser() -> argparse.ArgumentParser:
    """環境準備commandのparserを返す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("ensure", "setup"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("profile", choices=PROFILES, nargs="?", default="check")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """環境準備commandを実行する。"""
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "setup":
            setup(arguments.profile)
        else:
            changed = ensure(arguments.profile)
            print("依存を準備しました。" if changed else "依存は準備済みです。")
    except (OSError, RuntimeError) as error:
        print(str(error))
        return 2
    return 0


__all__ = ["PROFILES", "ensure", "main", "setup"]
