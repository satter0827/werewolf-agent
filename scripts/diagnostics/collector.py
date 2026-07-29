"""既存成果物を複製せず、人とAI向けの診断indexを生成する。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from scripts._infra.artifacts import LAYOUT, REPOSITORY_ROOT, publish_directory, staged_directory
from scripts._infra.process import utc_now, write_json


def collect() -> Path:
    """最新report、application log、容量を参照するdiagnostic viewを公開する。"""
    related = _latest_reports()
    observations: list[dict[str, object]] = []
    confirmed: list[dict[str, object]] = []
    unconfirmed: list[str] = []
    next_actions: list[str] = []
    state = "passed"
    for artifact in related:
        artifact_path = cast(str, artifact["path"])
        if artifact.get("integrity") == "invalid":
            state = "error"
            observations.append({"source": artifact_path, "state": "corrupted"})
            confirmed.append(
                {"source": artifact_path, "detail": "manifestのSHA-256と一致しません。"}
            )
            next_actions.append(f"{artifact_path}を再生成してください。")
            continue
        document = _read_json(REPOSITORY_ROOT / artifact_path)
        if document is None:
            state = "error"
            observations.append({"source": artifact_path, "state": "unreadable"})
            confirmed.append(
                {"source": artifact_path, "detail": "参照先reportをJSONとして読み取れません。"}
            )
            next_actions.append(f"{artifact_path}を再生成してください。")
            continue
        artifact_state = str(document.get("state", "unknown"))
        observations.append(
            {"source": artifact_path, "state": artifact_state, "run_id": document.get("run_id")}
        )
        if _state_priority(artifact_state) > _state_priority(state):
            state = artifact_state
        for cause in _object_list(document.get("confirmed_causes")):
            confirmed.append({"source": artifact_path, "detail": cause})
        unconfirmed.extend(str(item) for item in _object_list(document.get("unconfirmed_scope")))
        next_actions.extend(str(item) for item in _object_list(document.get("next_actions")))
    application = _application_log_summary()
    observations.extend(cast(list[dict[str, object]], application["observations"]))
    report = {
        "generated_at": utc_now().isoformat(),
        "state": state,
        "observations": observations,
        "confirmed_causes": confirmed,
        "hypotheses": [],
        "unconfirmed_scope": list(dict.fromkeys(unconfirmed)),
        "next_actions": list(dict.fromkeys(next_actions)),
        "correlation_ids": application["correlation_ids"],
        "related_artifacts": related,
        "artifact_inventory": _artifact_inventory(),
    }
    with staged_directory("diagnostics-current") as staged:
        write_json(staged / "report.json", report)
        (staged / "summary.md").write_text(_summary(report), encoding="utf-8")
        publish_directory(staged, LAYOUT.diagnostics / "current")
    return LAYOUT.diagnostics / "current" / "report.json"


def _latest_reports() -> list[dict[str, object]]:
    candidates = list(LAYOUT.operations.glob("*/*/report.json"))
    candidates.extend(LAYOUT.quality.glob("profiles/*/current/report.json"))
    candidates.extend(LAYOUT.reviews.rglob("report.json"))
    latest: dict[str, Path] = {}
    for path in candidates:
        if not path.is_file():
            continue
        owner = _report_owner(path)
        if owner not in latest or path.stat().st_mtime > latest[owner].stat().st_mtime:
            latest[owner] = path
    return [
        {
            "kind": owner,
            "path": path.relative_to(REPOSITORY_ROOT).as_posix(),
            "sha256": _sha256(path),
            "integrity": _manifest_integrity(path),
        }
        for owner, path in sorted(latest.items())
    ]


def _manifest_integrity(report: Path) -> str:
    manifest = _read_json(report.parent / "manifest.json")
    if manifest is None:
        return "unverified"
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        return "invalid"
    relative = report.relative_to(report.parent).as_posix()
    entry = next(
        (item for item in artifacts if isinstance(item, dict) and item.get("path") == relative),
        None,
    )
    if entry is None or not isinstance(entry.get("sha256"), str):
        return "invalid"
    return "verified" if entry["sha256"] == _sha256(report) else "invalid"


def _report_owner(path: Path) -> str:
    relative = path.relative_to(LAYOUT.root)
    parts = relative.parts
    if parts[0] == "operations":
        return "/".join(parts[:2])
    if parts[0] == "quality" and len(parts) >= 4 and parts[1] == "profiles":
        return "/".join(parts[:3])
    if parts[0] == "reviews":
        return "/".join(parts[:-2])
    return "/".join(parts[:-1])


def _application_log_summary() -> dict[str, object]:
    observations: list[dict[str, object]] = []
    trace_ids: set[str] = set()
    operation_ids: set[str] = set()
    for path in sorted((LAYOUT.logs / "application").glob("*.jsonl")):
        counts: dict[str, int] = {}
        actions: dict[str, int] = {}
        error_codes: dict[str, int] = {}
        latest_timestamp: str | None = None
        records = path.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
        for line in records:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                counts["INVALID"] = counts.get("INVALID", 0) + 1
                continue
            level = str(record.get("log.level", "UNKNOWN"))
            counts[level] = counts.get(level, 0) + 1
            action = record.get("event.action")
            if action:
                actions[str(action)] = actions.get(str(action), 0) + 1
            error_code = record.get("error.code")
            if error_code:
                error_codes[str(error_code)] = error_codes.get(str(error_code), 0) + 1
            timestamp = record.get("@timestamp")
            if timestamp:
                latest_timestamp = max(latest_timestamp or str(timestamp), str(timestamp))
            if record.get("trace.id"):
                trace_ids.add(str(record["trace.id"]))
            if record.get("operation.id"):
                operation_ids.add(str(record["operation.id"]))
        observations.append(
            {
                "source": path.relative_to(REPOSITORY_ROOT).as_posix(),
                "records_examined": len(records),
                "levels": counts,
                "event_actions": actions,
                "error_codes": error_codes,
                "latest_timestamp": latest_timestamp,
            }
        )
    return {
        "observations": observations,
        "correlation_ids": {
            "trace_ids": sorted(trace_ids),
            "operation_ids": sorted(operation_ids),
        },
    }


def _artifact_inventory() -> list[dict[str, object]]:
    inventory: list[dict[str, object]] = []
    if not LAYOUT.root.is_dir():
        return inventory
    for area in sorted(path for path in LAYOUT.root.iterdir() if path.is_dir()):
        files = [path for path in area.rglob("*") if path.is_file()]
        inventory.append(
            {
                "area": area.name,
                "files": len(files),
                "bytes": sum(path.stat().st_size for path in files),
                "classification": (
                    "reproducible" if area.name in {"cache", "runtime"} else "evidence"
                ),
            }
        )
    return inventory


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes())
    return digest.hexdigest()


def _object_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _state_priority(state: str) -> int:
    return {"passed": 0, "unknown": 0, "blocked": 1, "failed": 2, "error": 3}.get(state, 1)


def _summary(report: dict[str, object]) -> str:
    observations = _object_list(report["observations"])
    causes = _object_list(report["confirmed_causes"])
    scope = _object_list(report["unconfirmed_scope"])
    actions = _object_list(report["next_actions"])
    lines = ["# 現在の診断", "", f"- 判定: `{report['state']}`", "", "## 状況", ""]
    lines.extend(
        f"- `{item.get('source', 'unknown')}`: `{item.get('state', 'observed')}`"
        for item in observations
        if isinstance(item, dict)
    )
    lines.extend(["", "## 確認できた原因", ""])
    lines.extend(
        f"- `{item.get('source', 'unknown')}`: {item.get('detail')}"
        for item in causes
        if isinstance(item, dict)
    )
    if not causes:
        lines.append("- 確定した原因はありません。")
    lines.extend(["", "## 未確認範囲", ""])
    lines.extend(f"- {item}" for item in scope) if scope else lines.append("- ありません。")
    lines.extend(["", "## 次の操作", ""])
    lines.extend(f"- {item}" for item in actions) if actions else lines.append(
        "- 追加操作はありません。"
    )
    return "\n".join(lines) + "\n"


__all__ = ["collect"]
