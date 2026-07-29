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
from html.parser import HTMLParser
from pathlib import Path

from scripts._infra.artifacts import LAYOUT, publish_directory
from scripts._infra.process import (
    ARTIFACT_ROOT,
    REPOSITORY_ROOT,
    TEMPORARY_ROOT,
    remove_managed_path,
    remove_temporary_path,
    run_command,
)
from scripts.architecture import OUTPUT_ROOT as ARCHITECTURE_OUTPUT_ROOT
from scripts.architecture import PUBLIC_MODULES, write_outputs
from scripts.docs.inspection import inspect_documentation

DOCS_ROOT = REPOSITORY_ROOT / "docs"
OUTPUT_ROOT = ARTIFACT_ROOT / "outputs" / "docs"
INSPECTION_PATH = LAYOUT.reviews / "docs" / "inspection" / "report.json"


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
                    "message": result.output[-12000:],
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
        api_path = output_root / "reference" / "python-api.html"
        if result.returncode == 0:
            findings.extend(_python_api_html_findings(api_path))
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


class _PythonApiHtmlParser(HTMLParser):
    """生成HTMLから公開moduleとPython object構造を収集する。"""

    def __init__(self) -> None:
        super().__init__()
        self.anchors: set[str] = set()
        self.object_count = 0
        self.visible_text: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if identifier := attributes.get("id"):
            self.anchors.add(identifier)
        classes = set((attributes.get("class") or "").split())
        if tag == "dl" and "py" in classes and len(classes - {"py"}) > 0:
            self.object_count += 1
        if tag in {"script", "style"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.visible_text.append(data)


def _python_api_html_findings(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return [
            {
                "rule_id": "DOC-API-HTML-001",
                "message": "Python API HTML artifact is missing.",
                "path": "reference/python-api.html",
            }
        ]
    parser = _PythonApiHtmlParser()
    parser.feed(path.read_text(encoding="utf-8"))
    findings: list[dict[str, str]] = []
    for module in sorted(item.__name__ for item in PUBLIC_MODULES):
        anchor = f"module-{module}"
        if anchor not in parser.anchors:
            findings.append(
                {
                    "rule_id": "DOC-API-HTML-002",
                    "message": f"Public module anchor is missing: {anchor}",
                    "path": "reference/python-api.html",
                }
            )
    if parser.object_count == 0:
        findings.append(
            {
                "rule_id": "DOC-API-HTML-003",
                "message": "Structured Python objects are missing.",
                "path": "reference/python-api.html",
            }
        )
    visible = " ".join(parser.visible_text)
    for marker in (".. py:", ":canonical:"):
        if marker in visible:
            findings.append(
                {
                    "rule_id": "DOC-API-HTML-004",
                    "message": f"Raw autodoc directive is visible: {marker}",
                    "path": "reference/python-api.html",
                }
            )
    return findings


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
