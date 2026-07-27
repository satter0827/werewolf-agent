"""VS Codeの実行とデバッグに公開する選択式command。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from scripts._infra.artifacts import LAYOUT, REPOSITORY_ROOT
from scripts._infra.operations import prune_review_runs, write_bundle_manifest
from scripts._infra.process import (
    QUALITY_COMPOSE_PROJECT_NAME,
    quality_environment,
    utc_now,
)
from scripts.agents.review import preflight
from scripts.review.gameplay import gameplay_summary, generate_gameplay_evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("level", choices=("auto", "focus", "check", "release", "deep"))
    review = subparsers.add_parser("review")
    review.add_argument("kind", choices=("ui", "gameplay", "local-llm"))
    subparsers.add_parser("open-report")
    subparsers.add_parser("cleanup")
    arguments = parser.parse_args(argv)
    if arguments.command == "verify":
        extra = ["--confirm-deep"] if arguments.level == "deep" else []
        return _run([sys.executable, "-m", "scripts.quality", arguments.level, *extra])
    if arguments.command == "review":
        return _review(arguments.kind)
    if arguments.command == "open-report":
        return _open_latest_report()
    return _cleanup_owned_resources()


def _review(kind: str) -> int:
    """主観判定を行わず、読解用の証拠を選択生成する。"""
    root = LAYOUT.reviews / kind / f"{utc_now():%Y%m%dT%H%M%SZ}"
    root.mkdir(parents=True, exist_ok=True)
    (root / ".active").write_text("", encoding="utf-8")
    if kind == "ui":
        command = [sys.executable, "-m", "scripts.quality", "gate", "browser"]
    elif kind == "gameplay":
        evidence = generate_gameplay_evidence()
        transcript = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
        (root / "gameplay.json").write_text(transcript, encoding="utf-8")
        (root / "summary.md").write_text(gameplay_summary(evidence), encoding="utf-8")
        _finalize_review(root, kind, "passed")
        print(f"レビュー証拠: {root}")
        return 0
    else:
        return _review_local_llm(root)
    result = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=quality_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    transcript = result.stdout + result.stderr
    (root / "transcript.txt").write_text(transcript, encoding="utf-8")
    _finalize_review(root, kind, "passed" if result.returncode == 0 else "failed")
    print(transcript, end="")
    print(f"レビュー証拠: {root}")
    return result.returncode


def _review_local_llm(root: Path) -> int:
    """Local LLMを本番Agent graphまで通すpreflightへ委譲する。"""
    state, evidence = preflight()
    document = {"state": state, **evidence}
    transcript = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    (root / "preflight.json").write_text(transcript, encoding="utf-8")
    (root / "transcript.txt").write_text(transcript, encoding="utf-8")
    _finalize_review(root, "local-llm", state)
    print(transcript, end="")
    print(f"レビュー証拠: {root}")
    if state == "passed":
        return 0
    if state in {"degraded", "failed"}:
        return 1
    return 2


def _finalize_review(root: Path, kind: str, state: str) -> None:
    """Reviewを共通run bundleとして確定し、保持上限を適用する。"""
    summary = root / "summary.md"
    if not summary.exists():
        summary.write_text(
            f"# Review: {kind}\n\n- 判定: `{state}`\n",
            encoding="utf-8",
        )
    report = {
        "schema_version": 1,
        "run_id": root.name,
        "kind": kind,
        "state": state,
        "artifact_manifest": "manifest.json",
    }
    (root / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_bundle_manifest(root)
    (root / ".active").unlink(missing_ok=True)
    prune_review_runs()


def _open_latest_report() -> int:
    reports = sorted(
        (LAYOUT.quality / "profiles").glob("*/current/report.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        print("最新の品質reportがありません。先にVerifyを実行してください。", file=sys.stderr)
        return 2
    report = reports[0]
    if os.name == "nt":
        os.startfile(report)
    else:
        print(report)
    return 0


def _run(command: list[str]) -> int:
    return subprocess.call(command, cwd=REPOSITORY_ROOT)


def _cleanup_owned_resources() -> int:
    """品質runnerのbuildと固定Compose projectだけをcleanupする。"""
    result = _run([sys.executable, "-m", "scripts.quality", "clean"])
    if shutil.which("docker") is None:
        return result
    environment = dict(os.environ)
    environment["COMPOSE_PROJECT_NAME"] = QUALITY_COMPOSE_PROJECT_NAME
    cleanup = subprocess.call(
        ["docker", "compose", "--profile", "e2e", "down", "--volumes", "--remove-orphans"],
        cwd=REPOSITORY_ROOT,
        env=environment,
    )
    return result or cleanup


if __name__ == "__main__":
    raise SystemExit(main())
