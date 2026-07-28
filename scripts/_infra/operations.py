"""有限のrepository操作が共有するrun成果物契約。"""

from __future__ import annotations

import hashlib
import json
import shutil
import tomllib
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import uuid4

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

from scripts._infra.artifacts import LAYOUT, REPOSITORY_ROOT
from scripts._infra.process import redact, utc_now, write_json


def operation_run_id(kind: str) -> str:
    """衝突しないUTC基準のoperation run IDを返す。"""
    from os import getpid
    from uuid import uuid4

    return f"{utc_now():%Y%m%dT%H%M%SZ}-{kind}-{getpid()}-{uuid4().hex[:8]}"


def publish_operation(
    kind: str,
    run_id: str,
    report: object,
    summary: str,
    *,
    failure_logs: dict[str, str] | None = None,
) -> Path:
    """完了したoperationをreport、summary、manifestの一式で公開する。"""
    root = LAYOUT.operations / kind / run_id
    if root.exists():
        raise FileExistsError(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    scratch = root.with_name(f".{run_id}.{uuid4().hex}.staging")
    scratch.mkdir(parents=True, exist_ok=False)
    (scratch / ".active").write_text("", encoding="utf-8")
    (scratch / "logs").mkdir()
    maximum = _artifact_settings()["operation_failure_output_max_chars"]
    for stage, output in (failure_logs or {}).items():
        safe_name = "".join(
            character if character.isalnum() or character in "-_" else "-" for character in stage
        )
        path = scratch / "logs" / f"{safe_name}.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(redact(output)[-maximum:] + "\n", encoding="utf-8")
    value = (
        asdict(cast("DataclassInstance", report))
        if not isinstance(report, type) and is_dataclass(report)
        else report
    )
    write_json(scratch / "report.json", value)
    (scratch / "summary.md").write_text(summary.rstrip() + "\n", encoding="utf-8")
    write_bundle_manifest(scratch)
    (scratch / ".active").unlink()
    scratch.replace(root)
    _prune_operations()
    return root / "report.json"


def write_bundle_manifest(root: Path) -> None:
    """run directoryのfile hashとsizeをmanifestへ記録する。"""
    entries: list[dict[str, object]] = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        if path.name in {".active", "manifest.json"}:
            continue
        if path.parent.name == "logs":
            category = "failure-log"
        elif path.name == "report.json":
            category = "report"
        elif path.name == "summary.md":
            category = "summary"
        else:
            category = "evidence"
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "category": category,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    write_json(root / "manifest.json", {"schema_version": 1, "artifacts": entries})


def prune_review_runs() -> None:
    """完了したreview runとprivate evidenceへ保持上限を適用する。"""
    import time

    settings = _artifact_settings()
    keep = settings["review_runs_per_kind"]
    limit = settings["review_max_mib"] * 1024 * 1024
    private_age = settings["review_private_retention_days"] * 86400
    root = LAYOUT.reviews
    if not root.is_dir():
        return
    runs = _review_run_directories(root)
    now = time.time()
    for run in runs:
        if (run / ".active").exists():
            continue
        private = run / "private"
        if private.is_dir() and now - private.stat().st_mtime > private_age:
            shutil.rmtree(private)
            _refresh_manifest_after_retention(run)
    by_kind: dict[str, list[Path]] = {}
    for run in runs:
        if not (run / ".active").exists():
            by_kind.setdefault(_review_kind(root, run), []).append(run)
    retained: list[Path] = []
    for kind_runs in by_kind.values():
        ordered = sorted(
            kind_runs,
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        retained.extend(ordered[:keep])
        for expired in ordered[keep:]:
            shutil.rmtree(expired)
    retained = [path for path in retained if path.exists()]
    total = sum(_directory_size(path) for path in retained)
    for run in sorted(retained, key=lambda path: path.stat().st_mtime):
        if total <= limit:
            break
        private = run / "private"
        if not private.is_dir():
            continue
        before = _directory_size(run)
        shutil.rmtree(private)
        _refresh_manifest_after_retention(run)
        total -= before - _directory_size(run)
    newest = max(retained, key=lambda path: path.stat().st_mtime, default=None)
    for expired in sorted(retained, key=lambda path: path.stat().st_mtime):
        if total <= limit:
            break
        if expired == newest:
            continue
        size = _directory_size(expired)
        shutil.rmtree(expired)
        total -= size


def _review_run_directories(root: Path) -> list[Path]:
    return sorted(
        {manifest.parent for manifest in root.rglob("manifest.json") if manifest.is_file()}
    )


def _review_kind(root: Path, run: Path) -> str:
    parts = run.relative_to(root).parts
    return "/".join(parts[:-1]) if len(parts) > 1 else parts[0]


def _refresh_manifest_after_retention(run: Path) -> None:
    manifest_path = run / "manifest.json"
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(document, dict) or not isinstance(document.get("artifacts"), list):
        return
    document["artifacts"] = [
        artifact
        for artifact in document["artifacts"]
        if isinstance(artifact, dict)
        and isinstance(artifact.get("path"), str)
        and (run / artifact["path"]).is_file()
    ]
    document["retention_updated_at"] = utc_now().isoformat()
    write_json(manifest_path, document)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_settings() -> dict[str, int]:
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as stream:
        values = tomllib.load(stream)["tool"]["werewolf-artifacts"]
    return {key: int(value) for key, value in values.items()}


def _prune_operations() -> None:
    settings = _artifact_settings()
    keep = settings["operation_runs_per_kind"]
    limit = settings["operation_max_mib"] * 1024 * 1024
    root = LAYOUT.operations
    if not root.is_dir():
        return
    for kind in (path for path in root.iterdir() if path.is_dir()):
        runs = sorted(
            (path for path in kind.iterdir() if path.is_dir() and not (path / ".active").exists()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for expired in runs[keep:]:
            shutil.rmtree(expired)
    runs = sorted(
        (path for path in root.glob("*/*") if path.is_dir() and not (path / ".active").exists()),
        key=lambda path: path.stat().st_mtime,
    )
    total = sum(_directory_size(path) for path in runs)
    for expired in runs:
        if total <= limit:
            break
        size = _directory_size(expired)
        shutil.rmtree(expired)
        total -= size


def _directory_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


__all__ = [
    "operation_run_id",
    "prune_review_runs",
    "publish_operation",
    "write_bundle_manifest",
]
