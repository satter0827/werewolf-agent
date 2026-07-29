"""品質成果物の分類、manifest、参照整合性。"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import tomllib
from pathlib import Path

from scripts._infra.artifacts import LAYOUT, REPOSITORY_ROOT
from scripts._infra.process import write_json
from scripts.quality.models import GateResult
from scripts.versioning.versions import QUALITY_EVIDENCE_VERSION

EVIDENCE_ROOTS = frozenset(
    {
        "benchmarks",
        "browser",
        "contracts",
        "coverage",
        "outputs",
        "review",
        "test-results",
    }
)
DIAGNOSTIC_ROOTS = frozenset({"diagnostics", "logs"})
REPRODUCIBLE_SUFFIXES = frozenset({".mp4", ".webm"})


def artifact_category(relative: Path) -> str:
    """成果物pathから保持分類を返す。"""
    if relative.name in {"events.jsonl", "report.json", "summary.md"}:
        return "evidence"
    if relative.suffix.casefold() in REPRODUCIBLE_SUFFIXES:
        return "reproducible"
    if relative.parts and relative.parts[0] in EVIDENCE_ROOTS:
        return "evidence"
    if relative.parts and relative.parts[0] in DIAGNOSTIC_ROOTS:
        return "diagnostic"
    return "diagnostic"


def write_manifest(run_dir: Path, results: list[GateResult]) -> Path:
    """Run内の全成果物を改ざん検出可能なmanifestへ書く。"""
    producers: dict[str, str] = {}
    for result in results:
        if result.log:
            producers[result.log] = result.name
        producers.update({artifact: result.name for artifact in result.artifacts})
    entries: list[dict[str, object]] = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        relative = path.relative_to(run_dir)
        entries.append(
            {
                "path": relative.as_posix(),
                "producer": producers.get(relative.as_posix(), "quality-runner"),
                "category": artifact_category(relative),
                "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "retained": True,
                "omission_reason": None,
            }
        )
    manifest = run_dir / "manifest.json"
    write_json(
        manifest,
        {
            "schema_version": QUALITY_EVIDENCE_VERSION,
            "run_id": run_dir.name,
            "artifacts": entries,
        },
    )
    return manifest


def validate_references(run_dir: Path, results: list[GateResult]) -> list[str]:
    """Gate結果が参照するlogとartifactの実在を検査する。"""
    issues: list[str] = []
    for result in results:
        references = ([result.log] if result.log else []) + result.artifacts
        for reference in references:
            path = _reference_path(run_dir, reference)
            if not path.is_file():
                issues.append(f"{result.name}の成果物参照が存在しません: {reference}")
    return issues


def validate_retention_capacity(run_dir: Path) -> list[str]:
    """削除できない証拠がfailure保持上限を超える場合は契約違反にする。"""
    try:
        with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as stream:
            maximum = int(tomllib.load(stream)["tool"]["werewolf-quality"]["failure_run_max_mib"])
    except (KeyError, OSError, TypeError, ValueError, tomllib.TOMLDecodeError) as error:
        return [f"成果物保持上限を読み込めません: {error}"]
    protected = sum(
        path.stat().st_size
        for path in run_dir.rglob("*")
        if path.is_file() and artifact_category(path.relative_to(run_dir)) != "reproducible"
    )
    limit = maximum * 1024 * 1024
    if protected > limit:
        return [f"必須証拠 {protected} bytes が保持上限 {limit} bytes を超えています。"]
    return []


def manifest_paths(manifest: Path) -> set[str]:
    """Manifestに記録されたrun相対pathを返す。"""
    document = json.loads(manifest.read_text(encoding="utf-8"))
    artifacts = document.get("artifacts") if isinstance(document, dict) else None
    if not isinstance(artifacts, list):
        raise ValueError("manifest.artifactsが配列ではありません。")
    return {
        str(entry["path"])
        for entry in artifacts
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }


def _reference_path(run_dir: Path, reference: str) -> Path:
    snapshot = run_dir / reference
    if snapshot.is_file():
        return snapshot
    if reference.startswith("outputs/"):
        return LAYOUT.root / reference
    return snapshot


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "artifact_category",
    "manifest_paths",
    "validate_references",
    "validate_retention_capacity",
    "write_manifest",
]
