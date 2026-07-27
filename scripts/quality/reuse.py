"""決定的gateの成功証跡を内容fingerprintで再利用する。"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from scripts._infra.artifacts import LAYOUT, REPOSITORY_ROOT
from scripts.quality.models import Gate, GateResult, RunContext


def gate_fingerprint(context: RunContext, gate: Gate) -> str:
    """Command、依存環境、宣言入力からgate fingerprintを返す。"""
    digest = hashlib.sha256()
    header = {
        "command": gate.command,
        "cwd": str(gate.cwd.resolve()),
        "dependency": context.initial_dependency_fingerprint,
    }
    digest.update(json.dumps(header, sort_keys=True).encode())
    matched: set[Path] = set()
    for pattern in gate.inputs:
        matched.update(path for path in REPOSITORY_ROOT.glob(pattern) if path.is_file())
    for path in sorted(matched):
        digest.update(path.relative_to(REPOSITORY_ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def reuse_gate(context: RunContext, gate: Gate) -> GateResult | None:
    """検証できる同一fingerprintの成功結果を現在runへ複製する。"""
    if context.fresh or not gate.reusable:
        return None
    pointer = LAYOUT.quality / "profiles" / context.profile / "last-passed.json"
    try:
        reference = json.loads(pointer.read_text(encoding="utf-8"))
        report_path = LAYOUT.quality / str(reference["report"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        previous = next(item for item in report["results"] if item["name"] == gate.name)
    except (KeyError, OSError, StopIteration, TypeError, json.JSONDecodeError):
        return None
    fingerprint = gate_fingerprint(context, gate)
    if previous.get("state") != "passed" or previous.get("fingerprint") != fingerprint:
        return None
    source = report_path.parent
    paths = [value for value in previous.get("artifacts", []) if isinstance(value, str)]
    log = previous.get("log")
    if isinstance(log, str):
        paths.append(log)
    for relative in paths:
        source_path = source / relative
        if not source_path.is_file():
            return None
    for relative in paths:
        source_path = source / relative
        target = context.run_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)
    return GateResult(
        name=gate.name,
        description=gate.description,
        state="passed",
        duration_seconds=0.0,
        command=list(gate.command),
        returncode=0,
        log=log if isinstance(log, str) else None,
        message=f"成功証跡を再利用しました: {reference['run_id']}",
        artifacts=[value for value in previous.get("artifacts", []) if isinstance(value, str)],
        execution_origin="reused",
        source_run=str(reference["run_id"]),
        fingerprint=fingerprint,
    )


__all__ = ["gate_fingerprint", "reuse_gate"]
