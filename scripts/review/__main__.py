"""人が読解するためのレビュー証拠を生成する。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from scripts._infra.artifacts import LAYOUT, REPOSITORY_ROOT
from scripts._infra.operations import prune_review_runs, write_bundle_manifest
from scripts._infra.process import quality_environment, utc_now
from scripts.agents.review import preflight
from scripts.review.gameplay import gameplay_summary, generate_gameplay_evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("ui", "gameplay", "local-llm"))
    arguments = parser.parse_args(argv)
    return review(arguments.kind)


def review(kind: str) -> int:
    """主観判定を行わず、指定した読解用証拠を生成する。"""
    root = LAYOUT.reviews / kind / f"{utc_now():%Y%m%dT%H%M%SZ}"
    root.mkdir(parents=True, exist_ok=True)
    (root / ".active").write_text("", encoding="utf-8")
    if kind == "ui":
        result = subprocess.run(
            [sys.executable, "-m", "scripts.quality", "gate", "browser"],
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
        _finalize(root, kind, _quality_exit_state(result.returncode))
        print(transcript, end="")
        print(f"レビュー証拠: {root}")
        return result.returncode
    if kind == "gameplay":
        evidence = generate_gameplay_evidence()
        (root / "gameplay.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (root / "summary.md").write_text(gameplay_summary(evidence), encoding="utf-8")
        _finalize(root, kind, "passed")
        print(f"レビュー証拠: {root}")
        return 0
    return _review_local_llm(root)


def _quality_exit_state(returncode: int) -> str:
    if returncode == 0:
        return "passed"
    if returncode == 2:
        return "blocked"
    return "failed"


def _review_local_llm(root: Path) -> int:
    state, evidence = preflight()
    transcript = json.dumps({"state": state, **evidence}, ensure_ascii=False, indent=2) + "\n"
    (root / "preflight.json").write_text(transcript, encoding="utf-8")
    (root / "transcript.txt").write_text(transcript, encoding="utf-8")
    _finalize(root, "local-llm", state)
    print(transcript, end="")
    print(f"レビュー証拠: {root}")
    return 0 if state == "passed" else (1 if state in {"degraded", "failed"} else 2)


def _finalize(root: Path, kind: str, state: str) -> None:
    summary = root / "summary.md"
    if not summary.exists():
        summary.write_text(f"# Review: {kind}\n\n- 判定: `{state}`\n", encoding="utf-8")
    (root / "report.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": root.name,
                "kind": kind,
                "state": state,
                "artifact_manifest": "manifest.json",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_bundle_manifest(root)
    (root / ".active").unlink(missing_ok=True)
    prune_review_runs()


if __name__ == "__main__":
    raise SystemExit(main())
