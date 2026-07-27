"""開発スクリプトで共有するprocess実行と安全なfile操作。"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, TextIO

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = REPOSITORY_ROOT / ".werewolf-agent"
QUALITY_ROOT = ARTIFACT_ROOT / "quality"
QUALITY_COMPOSE_PROJECT_NAME = "werewolf-agent-quality"
TEMPORARY_ROOT = ARTIFACT_ROOT / "runtime" / "tmp"
TEMPORARY_CACHE_DIRECTORIES = (
    TEMPORARY_ROOT / "cache" / "mypy",
    TEMPORARY_ROOT / "cache" / "process",
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
_PUBLIC_ENVIRONMENT_KEYS = frozenset({"werewolf_supabase_publishable_key"})
_PRIVATE_KEYS = (
    "night_action",
    "private_state",
    "role",
    "target",
    "target_id",
)
_TOKEN_METRIC_KEYS = frozenset(
    {"completion_tokens", "input_tokens", "output_tokens", "prompt_tokens", "total_tokens"}
)
_SENSITIVE_KEY = rf"[A-Za-z0-9_]*(?:{'|'.join((*_SECRET_KEYS, *_PRIVATE_KEYS))})[A-Za-z0-9_]*"
_JSON_SECRET_PATTERN = re.compile(
    rf'(?i)("(?P<key>{_SENSITIVE_KEY})"\s*:\s*)'
    r'("(?:\\.|[^"\\])*"|null|true|false|-?\d+(?:\.\d+)?)'
)
_SECRET_PATTERN = re.compile(
    rf"(?i)(\b(?P<key>{_SENSITIVE_KEY})\b\s*[:=]\s*)"
    r"(SecretStr\([^)]*\)|'[^']*'|\"[^\"]*\"|[^\s,;)}&]+)"
)
_URL_CREDENTIAL_PATTERN = re.compile(
    r"(?i)([a-z][a-z0-9+.-]{0,31}+://[^\s:/@]{1,256}+:)([^\s@/]{1,256}+)(@)"
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[^\s\"']+")
_QUERY_SECRET_PATTERN = re.compile(
    r"(?i)([?&](?:access_token|api_key|apikey|password|refresh_token|token)=)[^&#\s\"']+"
)
_TEXT_ARTIFACT_SUFFIXES = frozenset({".html", ".json", ".jsonl", ".log", ".md", ".txt", ".xml"})
_REMOVE_ATTEMPTS = 5
_REMOVE_RETRY_SECONDS = 0.2
ISOLATION_ENVIRONMENT = {
    "ANONYMIZED_TELEMETRY": "false",
    "DO_NOT_TRACK": "1",
    "LANGCHAIN_TRACING_V2": "false",
    "OTEL_SDK_DISABLED": "true",
    "SUPABASE_TELEMETRY_DISABLED": "true",
    "WEREWOLF_LLM_PROVIDER": "fake",
    "WEREWOLF_WORKER_PAID_LLM_BASE_URL": "",
    "WEREWOLF_WORKER_PAID_LLM_MODEL": "fake-list-chat-model",
    "WEREWOLF_WORKER_PAID_LLM_PROVIDER": "fake",
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
    """Repository管理領域に一意なrun IDとscratch directoryを作成する。"""
    run_id = f"{utc_now():%Y%m%dT%H%M%SZ}-{profile}-{os.getpid()}"
    run_dir = TEMPORARY_ROOT / "quality" / "runs" / run_id
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
    redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", value)
    redacted = _QUERY_SECRET_PATTERN.sub(r"\1[REDACTED]", redacted)
    redacted = _URL_CREDENTIAL_PATTERN.sub(r"\1[REDACTED]\3", redacted)
    redacted = _JSON_SECRET_PATTERN.sub(_redact_json_secret, redacted)
    return _SECRET_PATTERN.sub(_redact_text_secret, redacted)


def _redact_json_secret(match: re.Match[str]) -> str:
    if match.group("key").casefold() in _TOKEN_METRIC_KEYS:
        return match.group(0)
    return f'{match.group(1)}"[REDACTED]"'


def _redact_text_secret(match: re.Match[str]) -> str:
    if match.group("key").casefold() in _TOKEN_METRIC_KEYS:
        return match.group(0)
    return f"{match.group(1)}[REDACTED]"


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
        "WEREWOLF_LOCAL_LLM_BASE_URL",
        "WEREWOLF_LOCAL_LLM_MODEL",
        "WEREWOLF_OPENAI_MODEL",
        "WEREWOLF_WORKER_PAID_LLM_PROVIDER",
        "WEREWOLF_WORKER_PAID_LLM_MODEL",
        "WEREWOLF_WORKER_PAID_LLM_BASE_URL",
    ):
        environment.pop(name, None)
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "PYTHONUTF8": "1",
        }
    )
    environment.update(ISOLATION_ENVIRONMENT)
    if run_dir is not None:
        prepare_temporary_directories()
        temporary_cache = TEMPORARY_ROOT / "cache"
        process_temporary = temporary_cache / "process"
        process_temporary.mkdir(parents=True, exist_ok=True)
        environment.update(
            {
                "COVERAGE_FILE": str(run_dir / "coverage" / ".coverage"),
                "HYPOTHESIS_STORAGE_DIRECTORY": str(temporary_cache / "hypothesis"),
                "MYPY_CACHE_DIR": str(temporary_cache / "mypy"),
                "PYTEST_ADDOPTS": "",
                "PYTEST_DEBUG_TEMPROOT": str(temporary_cache / "pytest" / "tmp"),
                "TEMP": str(process_temporary),
                "TMP": str(process_temporary),
                "TMPDIR": str(process_temporary),
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
    import psutil  # type: ignore[import-untyped]

    if process.poll() is not None:
        return
    try:
        parent = psutil.Process(process.pid)
        descendants = parent.children(recursive=True)
        for child in reversed(descendants):
            child.terminate()
        parent.terminate()
        psutil.wait_procs([*descendants, parent], timeout=5)
    except psutil.NoSuchProcess:
        return


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    """timeout後も残る子孫processを強制停止する。"""
    import psutil

    try:
        parent = psutil.Process(process.pid)
        targets = [*parent.children(recursive=True), parent]
        for target in reversed(targets):
            target.kill()
        psutil.wait_procs(targets, timeout=5)
    except psutil.NoSuchProcess:
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
