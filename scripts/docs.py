"""Inspect and build the Sphinx documentation independently from quality orchestration."""

from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import os
import posixpath
import re
import shutil
import sys
import time
import tomllib
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts._support import (
    ARTIFACT_ROOT,
    REPOSITORY_ROOT,
    TEMPORARY_ROOT,
    remove_managed_path,
    remove_temporary_path,
    run_command,
)
from scripts.architecture import OUTPUT_ROOT as ARCHITECTURE_OUTPUT_ROOT
from scripts.architecture import PUBLIC_MODULES, write_outputs

DOCS_ROOT = REPOSITORY_ROOT / "docs"
PYPROJECT_PATH = REPOSITORY_ROOT / "pyproject.toml"
OUTPUT_ROOT = ARTIFACT_ROOT / "build" / "docs"
INSPECTION_PATH = ARTIFACT_ROOT / "build" / "docs-inspection.json"
REQUIRED_LABELS = frozenset(
    {
        "build-release",
        "development",
        "operations",
        "requirements",
        "system-architecture",
        "verification",
    }
)
PUBLIC_API_MODULES = frozenset(module.__name__ for module in PUBLIC_MODULES)
_LABEL_PATTERN = re.compile(r"^\((?P<label>[a-z0-9][a-z0-9-]*)\)=$", re.MULTILINE)
_TOCTREE_PATTERN = re.compile(
    r"```\{toctree\}\s*\n(?P<body>.*?)```",
    re.DOTALL,
)
_AUTOMODULE_PATTERN = re.compile(r"```\{automodule\}\s+([a-zA-Z0-9_.]+)")
_DOCSTRING_SUPPRESSION_PATTERN = re.compile(
    r"#\s*(?:(?:ruff|flake8):\s*)?noqa"
    r"(?:\s*$|\s*:[^#]*(?:\bD\d*\b|\bDOC\d*\b|\bALL\b))",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class DocumentationFinding:
    """One actionable documentation structure violation."""

    rule_id: str
    message: str
    path: str


def inspect_documentation() -> dict[str, object]:
    """Inspect stable documentation contracts without constraining prose layout."""
    findings: list[DocumentationFinding] = []
    markdown_paths = sorted(DOCS_ROOT.rglob("*.md"))
    source_paths = [
        path for path in markdown_paths if "_generated" not in path.relative_to(DOCS_ROOT).parts
    ]
    relative_sources = {
        path.relative_to(DOCS_ROOT).with_suffix("").as_posix(): path for path in source_paths
    }

    entrypoint = DOCS_ROOT / "index.md"
    config = DOCS_ROOT / "conf.py"
    if not entrypoint.is_file():
        findings.append(
            DocumentationFinding("DOC-ENTRY-001", "Missing Sphinx root document.", "docs/index.md")
        )
    if not config.is_file():
        findings.append(
            DocumentationFinding("DOC-ENTRY-002", "Missing Sphinx configuration.", "docs/conf.py")
        )

    labels: dict[str, list[str]] = {}
    automodules: set[str] = set()
    reachable_graph: dict[str, set[str]] = {}
    for path in source_paths:
        relative = path.relative_to(DOCS_ROOT).with_suffix("").as_posix()
        text = path.read_text(encoding="utf-8")
        for label in _LABEL_PATTERN.findall(text):
            labels.setdefault(label, []).append(path.relative_to(REPOSITORY_ROOT).as_posix())
        automodules.update(_AUTOMODULE_PATTERN.findall(text))
        reachable_graph[relative] = _toctree_targets(path, text)
        if ":undoc-members:" in text:
            findings.append(
                DocumentationFinding(
                    "DOC-API-001",
                    "Published API reference cannot include undocumented members.",
                    path.relative_to(REPOSITORY_ROOT).as_posix(),
                )
            )

    for label, paths in sorted(labels.items()):
        if len(paths) > 1:
            findings.append(
                DocumentationFinding(
                    "DOC-LABEL-001",
                    f"Duplicate Sphinx label: {label}",
                    ", ".join(paths),
                )
            )
    for label in sorted(REQUIRED_LABELS - labels.keys()):
        findings.append(
            DocumentationFinding(
                "DOC-LIFECYCLE-001",
                f"Required lifecycle label is missing: {label}",
                "docs/design",
            )
        )

    reachable = _reachable_documents(reachable_graph, "index")
    for relative in sorted(relative_sources):
        if relative == "index" or relative in reachable:
            continue
        findings.append(
            DocumentationFinding(
                "DOC-NAVIGATION-001",
                "Published documentation is not reachable from the Sphinx index.",
                f"docs/{relative}.md",
            )
        )
    for source, targets in sorted(reachable_graph.items()):
        for target in sorted(targets):
            if target in relative_sources:
                continue
            findings.append(
                DocumentationFinding(
                    "DOC-NAVIGATION-002",
                    f"Toctree target does not exist: {target}",
                    f"docs/{source}.md",
                )
            )

    if automodules != PUBLIC_API_MODULES:
        findings.append(
            DocumentationFinding(
                "DOC-API-002",
                "Published automodule set must match the supported package entry points. "
                f"actual={sorted(automodules)}",
                "docs/reference",
            )
        )

    suppressions = _docstring_suppressions()
    for source_path, line in suppressions:
        findings.append(
            DocumentationFinding(
                "DOC-API-003",
                "Docstring checks cannot be suppressed in package source.",
                f"{source_path}:{line}",
            )
        )
    for location in _configured_docstring_suppressions():
        findings.append(
            DocumentationFinding(
                "DOC-API-004",
                "Ruff configuration cannot suppress docstring checks for package source.",
                location,
            )
        )

    return {
        "schema_version": 1,
        "status": "failed" if findings else "passed",
        "metrics": {
            "published_page_count": len(source_paths),
            "label_count": len(labels),
            "automodule_count": len(automodules),
        },
        "documents": sorted(relative_sources),
        "navigation": {
            source: sorted(targets) for source, targets in sorted(reachable_graph.items())
        },
        "labels": {label: paths for label, paths in sorted(labels.items())},
        "automodules": sorted(automodules),
        "findings": [asdict(finding) for finding in findings],
    }


def build_documentation() -> tuple[int, Path]:
    """Build fresh Sphinx HTML and a machine-readable documentation report."""
    if OUTPUT_ROOT.exists():
        remove_managed_path(OUTPUT_ROOT)
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
            str(OUTPUT_ROOT),
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
        index_path = OUTPUT_ROOT / "index.html"
        if result.returncode == 0 and not index_path.is_file():
            findings.append(
                {
                    "rule_id": "DOC-ARTIFACT-001",
                    "message": "Sphinx completed without the root HTML artifact.",
                    "path": index_path.relative_to(REPOSITORY_ROOT).as_posix(),
                }
            )
        report = {
            **inspection,
            "status": "failed" if findings else "passed",
            "artifacts": _artifact_list(OUTPUT_ROOT),
            "findings": findings,
        }
        report_path = OUTPUT_ROOT / "report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(report_path, report)
        return (1 if findings else 0), report_path
    finally:
        if stage_root.exists():
            remove_temporary_path(stage_root)
        if doctree_root.exists():
            remove_temporary_path(doctree_root)


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


def _toctree_targets(path: Path, text: str) -> set[str]:
    targets: set[str] = set()
    for match in _TOCTREE_PATTERN.finditer(text):
        for raw_line in match.group("body").splitlines():
            line = raw_line.strip()
            if not line or line.startswith(":"):
                continue
            if "<" in line and line.endswith(">"):
                line = line.rsplit("<", maxsplit=1)[1][:-1].strip()
            absolute = line.startswith("/")
            line = line.removeprefix("/")
            if line.endswith(".md"):
                line = line[:-3]
            if re.match(r"^[a-z][a-z0-9+.-]*://", line, re.IGNORECASE):
                continue
            if not absolute:
                parent = path.relative_to(DOCS_ROOT).parent.as_posix()
                if parent != ".":
                    line = f"{parent}/{line}"
            targets.add(posixpath.normpath(line))
    return targets


def _reachable_documents(graph: dict[str, set[str]], root: str) -> set[str]:
    visited: set[str] = set()
    pending = [root]
    while pending:
        current = pending.pop()
        for target in graph.get(current, set()):
            if target in visited:
                continue
            visited.add(target)
            pending.append(target)
    return visited


def _docstring_suppressions() -> list[tuple[str, int]]:
    suppressions: list[tuple[str, int]] = []
    source_root = REPOSITORY_ROOT / "src" / "werewolf_agent"
    for path in sorted(source_root.rglob("*.py")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _DOCSTRING_SUPPRESSION_PATTERN.search(line):
                suppressions.append((path.relative_to(REPOSITORY_ROOT).as_posix(), line_number))
    return suppressions


def _configured_docstring_suppressions() -> list[str]:
    with PYPROJECT_PATH.open("rb") as stream:
        configuration = tomllib.load(stream)
    return _docstring_configuration_suppressions(configuration)


def _docstring_configuration_suppressions(configuration: object) -> list[str]:
    if not isinstance(configuration, dict):
        return []
    tool = configuration.get("tool")
    if not isinstance(tool, dict):
        return []
    ruff = tool.get("ruff")
    if not isinstance(ruff, dict):
        return []
    lint = ruff.get("lint")
    if not isinstance(lint, dict):
        return []

    suppressions: list[str] = []
    for key in ("ignore", "extend-ignore"):
        if _contains_docstring_code(lint.get(key)):
            suppressions.append(f"pyproject.toml:tool.ruff.lint.{key}")
    for key in ("per-file-ignores", "extend-per-file-ignores"):
        per_file = lint.get(key)
        if not isinstance(per_file, dict):
            continue
        for pattern, codes in per_file.items():
            if (
                isinstance(pattern, str)
                and _pattern_targets_package(pattern)
                and _contains_docstring_code(codes)
            ):
                suppressions.append(f"pyproject.toml:tool.ruff.lint.{key}.{pattern}")
    return sorted(suppressions)


def _contains_docstring_code(value: object) -> bool:
    if isinstance(value, str):
        return value.upper() == "ALL" or value.upper().startswith("D")
    if isinstance(value, list):
        return any(_contains_docstring_code(item) for item in value)
    return False


def _pattern_targets_package(pattern: str) -> bool:
    normalized = pattern.replace("\\", "/")
    samples = (
        "src/werewolf_agent/__init__.py",
        "src/werewolf_agent/domain/game.py",
    )
    return any(fnmatch.fnmatch(path, normalized) for path in samples)


def _artifact_list(root: Path) -> list[str]:
    if not root.exists():
        return []
    return [
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
