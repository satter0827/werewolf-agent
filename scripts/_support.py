"""品質管理スクリプトで共有する小さな実行基盤。"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, TextIO

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPOSITORY_ROOT / ".werewolf-agent"
QUALITY_ROOT = ARTIFACT_ROOT / "quality"
TEMPORARY_ROOT = Path(tempfile.gettempdir()) / "werewolf-agent"
TEMPORARY_CACHE_DIRECTORIES = (
    TEMPORARY_ROOT / "cache" / "mypy",
    TEMPORARY_ROOT / "cache" / "pytest",
    TEMPORARY_ROOT / "mypy",
    TEMPORARY_ROOT / "pytest",
    TEMPORARY_ROOT / "sphinx",
    TEMPORARY_ROOT / "supabase",
)

_SECRET_KEYS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "service_role",
    "token",
)
_PUBLIC_ENVIRONMENT_KEYS = frozenset(
    {
        "vite_supabase_publishable_key",
        "werewolf_supabase_publishable_key",
    }
)
_PRIVATE_KEYS = (
    "night_action",
    "private_state",
    "role",
    "target",
    "target_id",
)
_SENSITIVE_KEY = rf"[A-Za-z0-9_]*(?:{'|'.join((*_SECRET_KEYS, *_PRIVATE_KEYS))})[A-Za-z0-9_]*"
_JSON_SECRET_PATTERN = re.compile(
    rf'(?i)("(?P<key>{_SENSITIVE_KEY})"\s*:\s*)'
    r'("(?:\\.|[^"\\])*"|null|true|false|-?\d+(?:\.\d+)?)'
)
_SECRET_PATTERN = re.compile(
    rf"(?i)(\b{_SENSITIVE_KEY}\b\s*[:=]\s*)"
    r"(SecretStr\([^)]*\)|'[^']*'|\"[^\"]*\"|[^\s,;)}]+)"
)
_URL_CREDENTIAL_PATTERN = re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^\s:/@]+:)([^\s@/]+)(@)")
_TEXT_ARTIFACT_SUFFIXES = frozenset({".json", ".jsonl", ".log", ".md", ".txt", ".xml"})
_REMOVE_ATTEMPTS = 5
_REMOVE_RETRY_SECONDS = 0.2
_BLOCKED_NETWORK_PROXY = "http://127.0.0.1:9"
_LOOPBACK_NO_PROXY = "127.0.0.1,localhost,::1"
OFFLINE_GUARD_ENVIRONMENT = {
    "ALL_PROXY": _BLOCKED_NETWORK_PROXY,
    "ANONYMIZED_TELEMETRY": "false",
    "DO_NOT_TRACK": "1",
    "HTTP_PROXY": _BLOCKED_NETWORK_PROXY,
    "HTTPS_PROXY": _BLOCKED_NETWORK_PROXY,
    "LANGCHAIN_TRACING_V2": "false",
    "NO_PROXY": _LOOPBACK_NO_PROXY,
    "OTEL_SDK_DISABLED": "true",
    "SUPABASE_TELEMETRY_DISABLED": "true",
    "WEREWOLF_LLM_PROVIDER": "fake",
    "all_proxy": _BLOCKED_NETWORK_PROXY,
    "http_proxy": _BLOCKED_NETWORK_PROXY,
    "https_proxy": _BLOCKED_NETWORK_PROXY,
    "no_proxy": _LOOPBACK_NO_PROXY,
}


class EnvironmentBlockedError(RuntimeError):
    """品質検証に必要なローカル環境が不足している。"""


@dataclass(frozen=True, slots=True)
class CommandResult:
    """子プロセスの実行結果。"""

    command: list[str]
    returncode: int
    duration_seconds: float
    output: str
    timed_out: bool = False


def utc_now() -> datetime:
    """UTCの現在時刻を返す。"""
    return datetime.now(UTC)


def create_run_directory(profile: str) -> tuple[str, Path]:
    """一意なrun IDと成果物ディレクトリを作成する。"""
    run_id = f"{utc_now():%Y%m%dT%H%M%SZ}-{profile}-{os.getpid()}"
    run_dir = QUALITY_ROOT / "runs" / run_id
    for relative in (
        "logs",
        "test-results",
        "coverage",
        "benchmarks",
        "browser",
    ):
        (run_dir / relative).mkdir(parents=True, exist_ok=True)
    return run_id, run_dir


def redact(value: str) -> str:
    """ログに含まれる代表的な秘密情報を伏せる。"""
    redacted = _URL_CREDENTIAL_PATTERN.sub(r"\1[REDACTED]\3", value)
    redacted = _JSON_SECRET_PATTERN.sub(r'\1"[REDACTED]"', redacted)
    return _SECRET_PATTERN.sub(r"\1[REDACTED]", redacted)


def redact_artifacts(root: Path) -> None:
    """機械可読成果物に含まれる秘密値とprivate stateを伏せる。"""
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in _TEXT_ARTIFACT_SUFFIXES:
            continue
        content = path.read_text(encoding="utf-8")
        sanitized = redact(content)
        if sanitized != content:
            path.write_text(sanitized, encoding="utf-8")


def quality_environment(
    *,
    run_dir: Path | None = None,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """外部providerとtelemetryを無効にした子プロセス環境を返す。"""
    environment = dict(os.environ)
    if extra:
        environment.update(extra)
    for name in tuple(environment):
        normalized = name.casefold()
        if normalized not in _PUBLIC_ENVIRONMENT_KEYS and any(
            secret in normalized for secret in _SECRET_KEYS
        ):
            environment.pop(name, None)
    for name in (
        "LANGCHAIN_ENDPOINT",
        "LANGCHAIN_PROJECT",
        "OPENAI_BASE_URL",
        "WEREWOLF_LLM_BASE_URL",
        "WEREWOLF_LLM_MODEL",
    ):
        environment.pop(name, None)
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "PYTHONUTF8": "1",
        }
    )
    environment.update(OFFLINE_GUARD_ENVIRONMENT)
    if run_dir is not None:
        prepare_temporary_directories()
        temporary_cache = TEMPORARY_ROOT / "cache"
        environment.update(
            {
                "COVERAGE_FILE": str(run_dir / "coverage" / ".coverage"),
                "MYPY_CACHE_DIR": str(temporary_cache / "mypy"),
                "PYTEST_ADDOPTS": "",
                "PYTEST_DEBUG_TEMPROOT": str(temporary_cache / "pytest" / "tmp"),
                "SUPABASE_HOME": str(TEMPORARY_ROOT / "supabase" / run_dir.name),
                "WEREWOLF_QUALITY_RUN_DIR": str(run_dir),
            }
        )
    return environment


def prepare_temporary_directories() -> None:
    """品質toolが必要とする一時cacheの親を準備する。"""
    for path in TEMPORARY_CACHE_DIRECTORIES:
        path.mkdir(parents=True, exist_ok=True)


def run_command(
    command: Sequence[str],
    *,
    timeout_seconds: int,
    environment: Mapping[str, str],
    output: TextIO | None = None,
    cwd: Path = REPOSITORY_ROOT,
) -> CommandResult:
    """子プロセスを実行し、timeout時は子孫を含めて停止する。"""
    started = time.monotonic()
    popen_kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=dict(environment),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            **popen_kwargs,
        )
        stdout, _ = process.communicate(timeout=timeout_seconds)
        text = stdout or ""
        if output is not None:
            output.write(redact(text))
        return CommandResult(
            command=list(command),
            returncode=process.returncode if process.returncode is not None else 1,
            duration_seconds=time.monotonic() - started,
            output=text,
        )
    except FileNotFoundError as error:
        raise EnvironmentBlockedError(f"実行ファイルが見つかりません: {command[0]}") from error
    except subprocess.TimeoutExpired:
        if process is None:
            raise
        _terminate_process_tree(process)
        try:
            stdout, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            _kill_process_tree(process)
            stdout, _ = process.communicate()
        else:
            _kill_process_tree(process)
        text = stdout or ""
        if output is not None:
            output.write(redact(text))
        return CommandResult(
            command=list(command),
            returncode=124,
            duration_seconds=time.monotonic() - started,
            output=text,
            timed_out=True,
        )
    except BaseException:
        if process is not None:
            _terminate_process_tree(process)
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                _kill_process_tree(process)
                process.communicate()
        raise


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """timeoutしたprocessと、その子孫processを停止する。"""
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    """timeout後も残る子孫processを強制停止する。"""
    if sys.platform == "win32":
        if process.poll() is None:
            process.kill()
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def write_json(path: Path, value: object) -> None:
    """JSONを原子的に保存する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_latest(run_id: str, profile: str, state: str, report_path: Path) -> None:
    """最新runへの参照だけを固定位置へ保存する。"""
    write_json(
        QUALITY_ROOT / "latest.json",
        {
            "run_id": run_id,
            "profile": profile,
            "state": state,
            "report": str(report_path.relative_to(REPOSITORY_ROOT)),
        },
    )


def command_result_dict(result: CommandResult) -> dict[str, object]:
    """CommandResultをreport向けの辞書へ変換する。"""
    return asdict(result)


def remove_managed_path(path: Path) -> None:
    """管理対象ルート内だけを削除する。"""
    _remove_path_within(ARTIFACT_ROOT, path)


def remove_temporary_path(path: Path) -> None:
    """品質用一時ルート内だけを削除する。"""
    _remove_path_within(TEMPORARY_ROOT, path)


def _remove_path_within(root: Path, path: Path) -> None:
    """指定ルートの子だけを再試行付きで削除する。"""
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path == resolved_root or resolved_root not in resolved_path.parents:
        raise ValueError(f"削除対象が管理領域外です: {path}")
    if path.is_dir():
        for attempt in range(_REMOVE_ATTEMPTS):
            try:
                shutil.rmtree(path, onerror=_retry_readonly_removal)
                break
            except OSError:
                if not path.exists():
                    break
                if attempt == _REMOVE_ATTEMPTS - 1:
                    raise
                time.sleep(_REMOVE_RETRY_SECONDS * (attempt + 1))
    elif path.exists():
        path.unlink()


def _retry_readonly_removal(
    function: Callable[[str], object],
    path: str,
    error_info: tuple[type[BaseException], BaseException, TracebackType],
) -> None:
    """Windowsの読み取り専用生成物だけ属性を解除して削除を再試行する。"""
    error = error_info[1]
    if not isinstance(error, PermissionError):
        raise error
    os.chmod(path, stat.S_IWRITE)
    function(path)
