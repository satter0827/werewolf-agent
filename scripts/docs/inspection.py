"""Sphinx文書構造と公開API契約の独立検査。"""

from __future__ import annotations

import fnmatch
import posixpath
import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts._infra.process import REPOSITORY_ROOT
from scripts.architecture import PUBLIC_MODULES

DOCS_ROOT = REPOSITORY_ROOT / "docs"
PYPROJECT_PATH = REPOSITORY_ROOT / "pyproject.toml"
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
_TOCTREE_PATTERN = re.compile(r"```\{toctree\}\s*\n(?P<body>.*?)```", re.DOTALL)
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


__all__ = ["DocumentationFinding", "inspect_documentation"]
