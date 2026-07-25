"""品質orchestrationから独立してSphinx文書を検査・構築する。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from scripts._infra.artifacts import publish_directory
from scripts._infra.process import (
    ARTIFACT_ROOT,
    REPOSITORY_ROOT,
    TEMPORARY_ROOT,
    remove_managed_path,
    remove_temporary_path,
    run_command,
)
from scripts.architecture import OUTPUT_ROOT as ARCHITECTURE_OUTPUT_ROOT
from scripts.architecture import write_outputs
from scripts.docs.inspection import inspect_documentation

DOCS_ROOT = REPOSITORY_ROOT / "docs"
OUTPUT_ROOT = ARTIFACT_ROOT / "build" / "docs"
INSPECTION_PATH = ARTIFACT_ROOT / "quality" / "manual" / "docs" / "report.json"


def build_documentation() -> tuple[int, Path]:
    """Build fresh Sphinx HTML and a machine-readable documentation report."""
    inspection = inspect_documentation()
    if inspection["status"] != "passed":
        _write_json(INSPECTION_PATH, inspection)
        return 1, INSPECTION_PATH
    if importlib.util.find_spec("sphinx") is None:
        report = {
            **inspection,
            "status": "blocked",
            "findings": [
                {
                    "rule_id": "DOC-ENVIRONMENT-001",
                    "message": "The Sphinx dependency group is not installed.",
                    "path": "pyproject.toml",
                }
            ],
        }
        _write_json(INSPECTION_PATH, report)
        return 2, INSPECTION_PATH

    architecture = write_outputs()
    if architecture["status"] != "passed":
        report = {
            **inspection,
            "status": "failed",
            "findings": architecture["findings"],
        }
        _write_json(INSPECTION_PATH, report)
        return 1, INSPECTION_PATH

    stage_root = TEMPORARY_ROOT / "docs" / f"{os.getpid()}-{time.time_ns()}"
    output_root = TEMPORARY_ROOT / "docs-build" / stage_root.name
    doctree_root = TEMPORARY_ROOT / "sphinx" / stage_root.name
    try:
        shutil.copytree(DOCS_ROOT, stage_root)
        generated = stage_root / "_generated" / "architecture"
        shutil.copytree(ARCHITECTURE_OUTPUT_ROOT, generated)
        command = (
            sys.executable,
            "-m",
            "sphinx",
            "-W",
            "--keep-going",
            "-n",
            "-b",
            "html",
            "-d",
            str(doctree_root),
            "-c",
            str(DOCS_ROOT),
            str(stage_root),
            str(output_root),
        )
        result = run_command(
            command,
            timeout_seconds=180,
            environment=dict(os.environ),
        )
        findings: list[dict[str, str]] = []
        if result.returncode != 0:
            findings.append(
                {
                    "rule_id": "DOC-BUILD-001",
                    "message": result.output[-4000:],
                    "path": "docs",
                }
            )
        index_path = output_root / "index.html"
        if result.returncode == 0 and not index_path.is_file():
            findings.append(
                {
                    "rule_id": "DOC-ARTIFACT-001",
                    "message": "Sphinx completed without the root HTML artifact.",
                    "path": "index.html",
                }
            )
        report = {
            **inspection,
            "status": "failed" if findings else "passed",
            "artifacts": _artifact_list(output_root),
            "findings": findings,
        }
        report_path = output_root / "report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(report_path, report)
        if findings:
            _write_json(INSPECTION_PATH, report)
            return 1, INSPECTION_PATH
        publish_directory(output_root, OUTPUT_ROOT)
        return 0, OUTPUT_ROOT / "report.json"
    finally:
        if stage_root.exists():
            remove_temporary_path(stage_root)
        if doctree_root.exists():
            remove_temporary_path(doctree_root)
        if output_root.exists():
            remove_temporary_path(output_root)


def clean_documentation() -> list[Path]:
    """Remove only documentation-owned generated artifacts."""
    removed: list[Path] = []
    for path in (OUTPUT_ROOT, INSPECTION_PATH):
        if not path.exists():
            continue
        remove_managed_path(path)
        removed.append(path)
    return removed


def build_parser() -> argparse.ArgumentParser:
    """Build the standalone documentation command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "clean", "inspect"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one standalone documentation operation."""
    command = build_parser().parse_args(argv).command
    if command == "clean":
        for path in clean_documentation():
            print(path)
        return 0
    if command == "inspect":
        inspection = inspect_documentation()
        _write_json(INSPECTION_PATH, inspection)
        print(INSPECTION_PATH)
        return 0 if inspection["status"] == "passed" else 1
    state, report_path = build_documentation()
    print(report_path)
    return state


def _artifact_list(root: Path) -> list[str]:
    if not root.exists():
        return []
    return [path.relative_to(root).as_posix() for path in sorted(root.rglob("*")) if path.is_file()]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
