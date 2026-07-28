"""品質成果物をreview bundleとして確定し、保持上限を適用する。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psutil  # type: ignore[import-untyped]
from filelock import FileLock, Timeout

from scripts._infra.artifacts import LAYOUT, REPOSITORY_ROOT
from scripts._infra.process import TEMPORARY_ROOT, write_json
from scripts.quality.artifacts import artifact_category

FAILURES_PER_SELECTOR = 2
FAILURE_BYTES_LIMIT = 100 * 1024 * 1024
ABANDONED_RUN_AGE_SECONDS = 300
RUN_OWNER_FILE = "run-owner.json"


def mark_run_active(run_dir: Path) -> Path:
    """実行processのidentityを記録し、並行runによる誤回収を防ぐ。"""
    process = psutil.Process(os.getpid())
    owner = run_dir / RUN_OWNER_FILE
    write_json(owner, {"pid": process.pid, "create_time": process.create_time()})
    return owner


def recover_abandoned_runs(*, now: float | None = None) -> list[Path]:
    """前回中断されたscratch runを診断可能なfailure bundleとして回収する。"""
    current = time.time() if now is None else now
    scratch_root = TEMPORARY_ROOT / "quality" / "runs"
    if not scratch_root.is_dir():
        return []
    recovered: list[Path] = []
    with _publication_lock():
        for run_dir in sorted(path for path in scratch_root.iterdir() if path.is_dir()):
            if current - run_dir.stat().st_mtime < ABANDONED_RUN_AGE_SECONDS:
                continue
            if _is_active_run(run_dir):
                continue
            selector = _selector_from_run_id(run_dir.name)
            target = LAYOUT.quality / "history" / selector / run_dir.name
            _ensure_interrupted_report(run_dir, selector)
            target.parent.mkdir(parents=True, exist_ok=True)
            _replace_directory(target)
            shutil.move(str(run_dir), target)
            _bound_failure(target, _retention_settings()[1])
            _prune_history(selector, _retention_settings()[0])
            recovered.append(target)
    return recovered


def _is_active_run(run_dir: Path) -> bool:
    owner = run_dir / RUN_OWNER_FILE
    if not owner.is_file():
        return False
    try:
        document = json.loads(owner.read_text(encoding="utf-8"))
        process = psutil.Process(int(document["pid"]))
        return abs(float(process.create_time()) - float(document["create_time"])) < 0.01
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError, psutil.Error):
        return False


def _selector_from_run_id(run_id: str) -> str:
    parts = run_id.split("-", maxsplit=2)
    return parts[1] if len(parts) == 3 else "interrupted"


def _ensure_interrupted_report(run_dir: Path, selector: str) -> None:
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    log = run_dir / "logs" / "interrupted.log"
    log.write_text("前回の品質実行は完了記録なしで中断されました。\n", encoding="utf-8")
    if not (run_dir / "events.jsonl").is_file():
        (run_dir / "events.jsonl").write_text(
            '{"event":"run_recovered","state":"error"}\n', encoding="utf-8"
        )
    write_json(
        run_dir / "report.json",
        {
            "schema_version": 3,
            "run_id": run_dir.name,
            "profile": selector,
            "state": "error",
            "execution": {"revision": None, "tree": None},
            "change": {
                "base_ref": None,
                "base_revision": None,
                "head_revision": None,
                "merge_base_revision": None,
                "changed_paths": [],
            },
            "workspace": {"dirty": None, "fingerprint": None},
            "artifact_manifest": "manifest.json",
            "results": [
                {
                    "name": "runner",
                    "description": "Interrupted quality runner",
                    "state": "error",
                    "duration_seconds": 0.0,
                    "log": "logs/interrupted.log",
                    "message": "完了記録のないrunを次回起動時に回収しました。",
                    "artifacts": [],
                }
            ],
        },
    )
    (run_dir / "summary.md").write_text(
        f"# 品質評価: {selector}\n\n- 判定: `error`\n- Run ID: `{run_dir.name}`\n",
        encoding="utf-8",
    )
    from scripts.quality.artifacts import write_manifest
    from scripts.quality.models import GateResult

    write_manifest(
        run_dir,
        [
            GateResult(
                "runner", "Interrupted quality runner", "error", 0.0, log="logs/interrupted.log"
            )
        ],
    )


def publish_run(run_dir: Path, selector: str, state: str) -> Path:
    """最新試行をcurrentへ公開し、最後の成功と履歴を独立管理する。"""
    non_success_runs, failure_bytes_limit = _retention_settings()
    with _publication_lock():
        profile_root = LAYOUT.quality / "profiles" / selector
        current = profile_root / "current"
        history = LAYOUT.quality / "history" / selector
        if current.is_dir():
            previous = _run_id(current)
            archived = history / previous
            history.mkdir(parents=True, exist_ok=True)
            _replace_directory(archived)
            current.replace(archived)
            if _last_passed_run_id(selector) == previous:
                write_json(
                    profile_root / "last-passed.json",
                    {
                        "run_id": previous,
                        "report": f"history/{selector}/{previous}/report.json",
                    },
                )
            if _run_state(archived) != "passed":
                _bound_failure(archived, failure_bytes_limit)
        _publish_complete_bundle(run_dir, current)
        if state == "passed":
            write_json(
                profile_root / "last-passed.json",
                {
                    "run_id": _run_id(current),
                    "report": f"profiles/{selector}/current/report.json",
                },
            )
        _prune_history(selector, non_success_runs)
        return current / "report.json"


def _publish_complete_bundle(source: Path, target: Path) -> None:
    """Run一式をatomicに最新review bundleへ置き換える。"""
    temporary = target.with_name(f".{target.name}.tmp")
    _replace_directory(temporary)
    temporary.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, temporary)
    _replace_directory(target)
    temporary.replace(target)
    shutil.rmtree(source)


def _run_id(root: Path) -> str:
    try:
        document = json.loads((root / "report.json").read_text(encoding="utf-8"))
        return str(document["run_id"])
    except (KeyError, OSError, TypeError, json.JSONDecodeError):
        return root.name


def _run_state(root: Path) -> str:
    try:
        document = json.loads((root / "report.json").read_text(encoding="utf-8"))
        return str(document["state"])
    except (KeyError, OSError, TypeError, json.JSONDecodeError):
        return "error"


def _bound_failure(root: Path, limit_bytes: int = FAILURE_BYTES_LIMIT) -> None:
    """再生成可能な大容量成果物だけを容量上限まで削減する。"""
    files = [path for path in root.rglob("*") if path.is_file()]
    total = sum(path.stat().st_size for path in files)
    omitted: list[tuple[str, int]] = []
    removable = sorted(
        (path for path in files if artifact_category(path.relative_to(root)) == "reproducible"),
        key=lambda path: path.stat().st_size,
        reverse=True,
    )
    for path in removable:
        if total <= limit_bytes:
            break
        size = path.stat().st_size
        omitted.append((path.relative_to(root).as_posix(), size))
        total -= size
        path.unlink()
    _record_retention(root, omitted, limit_bytes, total > limit_bytes)


def _record_retention(
    root: Path,
    omitted: list[tuple[str, int]],
    limit_bytes: int,
    limit_exceeded: bool,
) -> None:
    report_path = root / "report.json"
    document = json.loads(report_path.read_text(encoding="utf-8"))
    document["retention"] = {
        "omitted_artifacts": [path for path, _size in omitted],
        "omitted_count": len(omitted),
        "omitted_bytes": sum(size for _path, size in omitted),
        "limit_bytes": limit_bytes,
        "limit_exceeded": limit_exceeded,
    }
    report_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    omitted_paths = {path for path, _size in omitted}
    for entry in manifest.get("artifacts", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("path") in omitted_paths:
            entry["retained"] = False
            entry["omission_reason"] = "failure bundle size limit"
        if entry.get("path") == "report.json":
            entry["bytes"] = report_path.stat().st_size
            entry["sha256"] = _sha256(report_path)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prune_history(selector: str, keep_non_success: int = FAILURES_PER_SELECTOR) -> None:
    root = LAYOUT.quality / "history" / selector
    if not root.is_dir():
        return
    last_passed = _last_passed_run_id(selector)
    runs = sorted(
        (path for path in root.iterdir() if path.is_dir()),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    non_success = 0
    for path in runs:
        if path.name == last_passed:
            continue
        if _run_state(path) != "passed" and non_success < keep_non_success:
            non_success += 1
            continue
        shutil.rmtree(path)


def _last_passed_run_id(selector: str) -> str | None:
    pointer = LAYOUT.quality / "profiles" / selector / "last-passed.json"
    try:
        document = json.loads(pointer.read_text(encoding="utf-8"))
        return str(document["run_id"])
    except (KeyError, OSError, TypeError, json.JSONDecodeError):
        return None


def _retention_settings() -> tuple[int, int]:
    """pyproject.tomlから保持件数と容量上限を取得する。"""
    try:
        with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as stream:
            quality = tomllib.load(stream)["tool"]["werewolf-quality"]
        count = int(quality["failure_runs_per_selector"])
        limit = int(quality["failure_run_max_mib"]) * 1024 * 1024
    except (KeyError, OSError, TypeError, ValueError, tomllib.TOMLDecodeError):
        return FAILURES_PER_SELECTOR, FAILURE_BYTES_LIMIT
    if count < 1 or limit < 1:
        return FAILURES_PER_SELECTOR, FAILURE_BYTES_LIMIT
    return count, limit


@contextmanager
def _publication_lock() -> Iterator[None]:
    """成果物確定とretentionの区間だけprocess間lockを取得する。"""
    LAYOUT.quality.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(LAYOUT.quality / ".publish.lock", timeout=10):
            yield
    except Timeout as error:
        raise TimeoutError("品質成果物の公開lockを取得できませんでした。") from error


def _replace_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


__all__ = [
    "ABANDONED_RUN_AGE_SECONDS",
    "FAILURES_PER_SELECTOR",
    "FAILURE_BYTES_LIMIT",
    "mark_run_active",
    "publish_run",
    "recover_abandoned_runs",
]
