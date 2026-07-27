"""Lock fileに従って必要な開発依存だけを準備する。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from filelock import FileLock, Timeout

from scripts._infra.process import (
    ARTIFACT_ROOT,
    QUALITY_COMPOSE_PROJECT_NAME,
    REPOSITORY_ROOT,
)
from scripts.supabase.constants import LOCAL_EXCLUDED_SERVICES_CSV, REQUIRED_LOCAL_IMAGES

STATE_ROOT = ARTIFACT_ROOT / "runtime" / "environment"
LOCK_PATH = STATE_ROOT / "setup.lock"
PROFILES = ("quick", "check", "release", "deep")
PYTHON_INPUTS = ("pyproject.toml", "uv.lock")
RELEASE_INPUTS = (
    "compose.yaml",
    "docker",
    "scripts",
    "src",
    "supabase",
)
E2E_COMPOSE_SERVICES = (
    "api",
    "worker",
    "streamlit",
    "e2e",
    "migrate",
)
RUNTIME_IMAGE = "werewolf-agent-quality-runtime:latest"


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
    try:
        completed = subprocess.run(
            [executable, *command[1:]],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    return completed.stdout.strip() if completed.returncode == 0 else "unavailable"


def dependency_fingerprint(profile: str) -> str:
    """Lock、tool version、release入力から依存環境fingerprintを返す。"""
    digest = hashlib.sha256()
    inputs = [REPOSITORY_ROOT / relative for relative in PYTHON_INPUTS]
    if profile in {"release", "deep"}:
        for relative in RELEASE_INPUTS:
            path = REPOSITORY_ROOT / relative
            inputs.extend(
                candidate
                for candidate in ([path] if path.is_file() else path.rglob("*"))
                if candidate.is_file() and not {"__pycache__", "dist"}.intersection(candidate.parts)
            )
    for path in sorted(set(inputs)):
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        digest.update(relative.encode())
        digest.update(path.read_bytes())
    for value in (
        profile,
        _version(("uv", "--version")),
        _version(("docker", "--version")) if profile in {"release", "deep"} else "",
        _version(("supabase", "--version")) if profile in {"release", "deep"} else "",
    ):
        digest.update(value.encode())
    return digest.hexdigest()


def python_installation_fingerprint() -> str:
    """Installed distributionの名前・version・RECORDを固定順でhash化する。"""
    digest = hashlib.sha256()
    records: list[tuple[str, str, str]] = []
    for distribution in importlib.metadata.distributions():
        name = re.sub(r"[-_.]+", "-", distribution.metadata["Name"].casefold())
        record_text = distribution.read_text("RECORD")
        record_hash = hashlib.sha256((record_text or "MISSING").encode()).hexdigest()
        records.append((name, distribution.version, record_hash))
    for entry in sorted(records):
        digest.update("\0".join(entry).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _state_path(profile: str) -> Path:
    return STATE_ROOT / f"{profile}.json"


def _ready(profile: str, fingerprint: str) -> bool:
    state_path = _state_path(profile)
    if not (REPOSITORY_ROOT / ".venv").is_dir():
        return False
    if not state_path.is_file():
        return False
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    state_matches = isinstance(state, dict) and state == {
        "fingerprint": fingerprint,
        "profile": profile,
    }
    return state_matches and _release_environment_ready(profile)


def required_release_images() -> tuple[str, ...]:
    """Release準備が現在のDocker contextへ作成するimageを返す。"""
    compose_images = tuple(
        f"{QUALITY_COMPOSE_PROJECT_NAME}-{service}" for service in E2E_COMPOSE_SERVICES
    )
    return (*REQUIRED_LOCAL_IMAGES, *compose_images, RUNTIME_IMAGE)


def _release_environment_ready(profile: str) -> bool:
    """Release系profileのdaemonと必須imageが現在のcontextに存在するか返す。"""
    if profile not in {"release", "deep"}:
        return True
    docker = shutil.which("docker")
    if docker is None or not _command_succeeds((docker, "info")):
        return False
    return all(
        _command_succeeds((docker, "image", "inspect", image))
        for image in required_release_images()
    )


def _command_succeeds(command: Sequence[str]) -> bool:
    """準備済み判定用の読取commandが成功したか返す。"""
    try:
        completed = subprocess.run(
            list(command),
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def setup(profile: str = "check") -> None:
    """指定profileに必要な依存をlockに従って準備する。"""
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(LOCK_PATH, timeout=600):
            _setup_locked(profile)
    except Timeout as error:
        raise RuntimeError("依存環境の準備lockを取得できませんでした。") from error


def _setup_locked(profile: str) -> None:
    """Process間lock内で指定profileの依存を準備する。"""
    uv = shutil.which("uv") or "uv"
    _run((uv, "sync", "--frozen", "--all-groups", "--all-extras"))
    if profile in {"release", "deep"}:
        docker = shutil.which("docker")
        supabase = shutil.which("supabase")
        if docker is None:
            raise RuntimeError("releaseにはDockerが必要です。")
        if supabase is None:
            raise RuntimeError("releaseにはSupabase CLIが必要です。")
        _run((supabase, "stop", "--no-backup"), quiet=True)
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
                *E2E_COMPOSE_SERVICES,
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
                RUNTIME_IMAGE,
                ".",
            )
        )
    fingerprint = dependency_fingerprint(profile)
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
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(LOCK_PATH, timeout=600):
            fingerprint = dependency_fingerprint(profile)
            if _ready(profile, fingerprint):
                return False
            _setup_locked(profile)
            return True
    except Timeout as error:
        raise RuntimeError("依存環境の準備lockを取得できませんでした。") from error


def is_ready(profile: str) -> bool:
    """現在のlock・source fingerprintに対応する環境が準備済みか返す。"""
    if profile not in PROFILES:
        raise ValueError(f"未定義の環境profileです: {profile}")
    return _ready(profile, dependency_fingerprint(profile))


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


__all__ = [
    "PROFILES",
    "RUNTIME_IMAGE",
    "dependency_fingerprint",
    "ensure",
    "is_ready",
    "main",
    "python_installation_fingerprint",
    "required_release_images",
    "setup",
]
