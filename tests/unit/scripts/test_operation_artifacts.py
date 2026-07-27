"""有限operationの共通成果物契約。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from scripts._infra import operations
from scripts._infra.artifacts import ArtifactLayout


def test_operation_bundle_contains_redacted_report_summary_log_and_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    layout = ArtifactLayout(tmp_path / ".werewolf-agent")
    monkeypatch.setattr(operations, "LAYOUT", layout)
    monkeypatch.setattr(
        operations,
        "_artifact_settings",
        lambda: {
            "operation_runs_per_kind": 10,
            "operation_max_mib": 50,
            "operation_failure_output_max_chars": 20,
            "review_runs_per_kind": 3,
            "review_max_mib": 100,
            "review_private_retention_days": 7,
        },
    )

    report = operations.publish_operation(
        "environment",
        "run-1",
        {"state": "error", "run_id": "run-1"},
        "# Summary",
        failure_logs={"docker-info": "prefix api_key=secret useful-tail"},
    )

    root = report.parent
    assert {path.name for path in root.iterdir()} == {
        "logs",
        "manifest.json",
        "report.json",
        "summary.md",
    }
    assert "secret" not in (root / "logs" / "docker-info.log").read_text(encoding="utf-8")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert {item["path"] for item in manifest["artifacts"]} == {
        "logs/docker-info.log",
        "report.json",
        "summary.md",
    }
    assert {item["category"] for item in manifest["artifacts"]} == {
        "failure-log",
        "report",
        "summary",
    }


def test_operation_retention_keeps_configured_run_count(tmp_path: Path, monkeypatch) -> None:
    layout = ArtifactLayout(tmp_path / ".werewolf-agent")
    monkeypatch.setattr(operations, "LAYOUT", layout)
    monkeypatch.setattr(
        operations,
        "_artifact_settings",
        lambda: {
            "operation_runs_per_kind": 2,
            "operation_max_mib": 50,
            "operation_failure_output_max_chars": 20000,
            "review_runs_per_kind": 3,
            "review_max_mib": 100,
            "review_private_retention_days": 7,
        },
    )
    for index in range(3):
        operations.publish_operation(
            "environment",
            f"run-{index}",
            {"state": "passed", "run_id": f"run-{index}"},
            "summary",
        )
    assert len(list((layout.operations / "environment").iterdir())) == 2
    assert all((run / "logs").is_dir() for run in (layout.operations / "environment").iterdir())


def test_operation_retention_does_not_remove_active_run(tmp_path: Path, monkeypatch) -> None:
    layout = ArtifactLayout(tmp_path / ".werewolf-agent")
    monkeypatch.setattr(operations, "LAYOUT", layout)
    monkeypatch.setattr(
        operations,
        "_artifact_settings",
        lambda: {
            "operation_runs_per_kind": 1,
            "operation_max_mib": 50,
            "operation_failure_output_max_chars": 20000,
            "review_runs_per_kind": 3,
            "review_max_mib": 100,
            "review_private_retention_days": 7,
        },
    )
    active = layout.operations / "environment" / "active-run"
    active.mkdir(parents=True)
    (active / ".active").write_text("", encoding="utf-8")

    operations.publish_operation(
        "environment",
        "completed-run",
        {"state": "passed", "run_id": "completed-run"},
        "summary",
    )

    assert active.is_dir()
    assert (layout.operations / "environment" / "completed-run").is_dir()


def test_review_retention_handles_nested_kinds_and_protects_active_private_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    layout = ArtifactLayout(tmp_path / ".werewolf-agent")
    monkeypatch.setattr(operations, "LAYOUT", layout)
    monkeypatch.setattr(
        operations,
        "_artifact_settings",
        lambda: {
            "operation_runs_per_kind": 10,
            "operation_max_mib": 50,
            "operation_failure_output_max_chars": 20000,
            "review_runs_per_kind": 1,
            "review_max_mib": 100,
            "review_private_retention_days": 7,
        },
    )
    kind = layout.reviews / "agents" / "runs"
    old = kind / "old"
    current = kind / "current"
    active = kind / "active"
    for run in (old, current, active):
        (run / "private").mkdir(parents=True)
        (run / "manifest.json").write_text("{}", encoding="utf-8")
    (active / ".active").write_text("", encoding="utf-8")
    expired = time.time() - 8 * 86400
    os.utime(active / "private", (expired, expired))
    os.utime(old, (expired - 10, expired - 10))

    operations.prune_review_runs()

    assert not old.exists()
    assert current.exists()
    assert (active / "private").exists()


def test_private_retention_removes_stale_manifest_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    layout = ArtifactLayout(tmp_path / ".werewolf-agent")
    monkeypatch.setattr(operations, "LAYOUT", layout)
    monkeypatch.setattr(
        operations,
        "_artifact_settings",
        lambda: {
            "operation_runs_per_kind": 10,
            "operation_max_mib": 50,
            "operation_failure_output_max_chars": 20000,
            "review_runs_per_kind": 3,
            "review_max_mib": 100,
            "review_private_retention_days": 7,
        },
    )
    run = layout.reviews / "agents" / "runs" / "run"
    (run / "private").mkdir(parents=True)
    (run / "public.txt").write_text("public", encoding="utf-8")
    (run / "private" / "trace.json").write_text("{}", encoding="utf-8")
    operations.write_bundle_manifest(run)
    expired = time.time() - 8 * 86400
    os.utime(run / "private", (expired, expired))

    operations.prune_review_runs()

    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert {artifact["path"] for artifact in manifest["artifacts"]} == {"public.txt"}
    assert "retention_updated_at" in manifest
