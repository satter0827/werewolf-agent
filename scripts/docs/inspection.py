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
STYLE_PATH = Path(__file__).with_name("style.toml")
REQUIRED_LABELS = frozenset(
    {
        "build-release",
        "development",
        "evidence-diagnostics",
        "operations",
        "requirements",
        "system-architecture",
        "verification",
    }
)
PUBLIC_API_MODULES = frozenset(module.__name__ for module in PUBLIC_MODULES)
CANONICAL_DOCUMENT_PATHS = (
    REPOSITORY_ROOT / "README.md",
    REPOSITORY_ROOT / "CONTRIBUTING.md",
    REPOSITORY_ROOT / "SECURITY.md",
    REPOSITORY_ROOT / "scripts" / "README.md",
)
QUALITY_COMMAND_OWNERS = frozenset({"AGENTS.md", "README.md", "scripts/README.md"})
OBSOLETE_REFERENCES = (
    "src/werewolf_agent/interfaces",
    "interfaces/worker",
    "application/resources/game",
    "application/resources/presentation",
    ".werewolf-agent/quality/latest",
    "docs/notes/assets/streamlit-ui",
    "docs/notes/design-qa.md",
    "docs/notes/development.md",
    "docs/notes/streamlit-browser-qa.md",
    "docs/notes/streamlit-ui-design-history.md",
    "docs/notes/streamlit-ui.md",
    "docs/notes/streamlit-zero-based-review.md",
    "frontend/package.json",
    "frontend/src/",
    "generated openapi client",
    "node.js",
    "npm",
    "react",
)
OBSOLETE_REFERENCE_ALLOWLIST = {
    "docs/notes/retired-browser-ui-reintroduction.md": frozenset(
        {"frontend/package.json", "frontend/src/", "node.js", "npm", "react"}
    )
}
_REPOSITORY_PATH_PREFIXES = (
    ".github/",
    ".streamlit/",
    ".vscode/",
    "contracts/",
    "docker/",
    "docs/",
    "scripts/",
    "src/",
    "supabase/",
    "tests/",
)
_PACKAGE_PATH_PREFIXES = (
    "adapters/",
    "agents/",
    "api/",
    "application/",
    "clients/",
    "contracts/",
    "domain/",
    "observability/",
    "security/",
    "settings/",
    "worker/",
)
_REPOSITORY_ROOT_FILES = frozenset(
    {
        ".env.example",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "README.md",
        "SECURITY.md",
        "compose.yaml",
        "pyproject.toml",
        "uv.lock",
    }
)
_LABEL_PATTERN = re.compile(r"^\((?P<label>[a-z0-9][a-z0-9-]*)\)=$", re.MULTILINE)
_TOCTREE_PATTERN = re.compile(r"```\{toctree\}\s*\n(?P<body>.*?)```", re.DOTALL)
_AUTOMODULE_PATTERN = re.compile(r"```\{automodule\}\s+([a-zA-Z0-9_.]+)")
_INLINE_CODE_PATTERN = re.compile(r"`(?P<value>[^`\n]+)`")
_MARKDOWN_LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\((?P<target>[^)]+)\)")
_VERIFICATION_COMMAND_PATTERN = re.compile(
    r"(?:python\s+-m\s+scripts\.(?:architecture|docs|environment|quality)"
    r"|scripts\.(?:architecture|docs|environment|quality)\s"
    r"|werewolf-agent\s+system\s+doctor"
    r"|ruff\s+(?:check|format)"
    r"|mypy\s+--"
    r"|pytest(?:\s+-|\s*$))",
    re.MULTILINE,
)
_DOCSTRING_SUPPRESSION_PATTERN = re.compile(
    r"#\s*(?:(?:ruff|flake8):\s*)?noqa"
    r"(?:\s*$|\s*:[^#]*(?:\bD\d*\b|\bDOC\d*\b|\bALL\b))",
    re.IGNORECASE,
)
_CODE_FENCE_PATTERN = re.compile(r"^```.*?^```\s*$", re.MULTILINE | re.DOTALL)
_INLINE_CODE_PATTERN_FOR_STYLE = re.compile(r"`[^`\n]+`")
_MARKDOWN_TARGET_PATTERN = re.compile(r"(?<=\]\()[^)]+(?=\))")
_SPHINX_LABEL_PATTERN = re.compile(r"^\([a-z0-9-]+\)=\s*$", re.MULTILINE)
_POLITE_SENTENCE_PATTERN = re.compile(r"(?:です|ます|ください)(?:。|$)", re.MULTILINE)
_INLINE_CODE_SPACING_PATTERN = re.compile(
    r"(?:[ぁ-んァ-ヶ一-龠々][ \t]+`|`[ \t]+[ぁ-んァ-ヶ一-龠々])"
)
_JAPANESE_WORD_SPACING_PATTERN = re.compile(r"[ぁ-んァ-ヶ一-龠々ー][ \t]+[ぁ-んァ-ヶ一-龠々ー]")


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
        path
        for path in markdown_paths
        if "_generated" not in path.relative_to(DOCS_ROOT).parts and path.name != "AGENTS.md"
    ]
    canonical_paths = [path for path in CANONICAL_DOCUMENT_PATHS if path.is_file()]
    agent_paths = sorted(
        path
        for path in REPOSITORY_ROOT.rglob("AGENTS.md")
        if not {".git", ".venv", ".werewolf-agent"}.intersection(
            path.relative_to(REPOSITORY_ROOT).parts
        )
    )
    audited_paths = list(dict.fromkeys([*canonical_paths, *source_paths, *agent_paths]))
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
    else:
        configuration = config.read_text(encoding="utf-8")
        required_configuration = (
            'html_theme = "furo"',
            'language = "ja"',
            'html_search_language = "ja"',
            'myst_enable_extensions = ["colon_fence"]',
            '"sphinx_copybutton"',
            '"sphinx_design"',
        )
        for required in required_configuration:
            if required in configuration:
                continue
            findings.append(
                DocumentationFinding(
                    "DOC-CONFIG-001",
                    f"Missing generated documentation configuration: {required}",
                    "docs/conf.py",
                )
            )
        if "alabaster" in configuration:
            findings.append(
                DocumentationFinding(
                    "DOC-CONFIG-002",
                    "Obsolete Alabaster configuration is not allowed.",
                    "docs/conf.py",
                )
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

    checked_reference_count = 0
    style_check_count = 0
    style = _style_configuration()
    for path in audited_paths:
        text = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(REPOSITORY_ROOT).as_posix()
        for reference, offset in _local_markdown_links(text):
            checked_reference_count += 1
            markdown_target = (path.parent / reference).resolve()
            if markdown_target.exists() and _is_within_repository(markdown_target):
                continue
            findings.append(
                DocumentationFinding(
                    "DOC-PATH-001",
                    f"Local Markdown target does not exist: {reference}",
                    f"{relative_path}:{_line_number(text, offset)}",
                )
            )
        for reference, offset in _repository_path_references(text):
            checked_reference_count += 1
            repository_target = _repository_reference_target(reference)
            if repository_target is not None and repository_target.exists():
                continue
            findings.append(
                DocumentationFinding(
                    "DOC-PATH-002",
                    f"Repository path does not exist: {reference}",
                    f"{relative_path}:{_line_number(text, offset)}",
                )
            )
        lowered = text.lower()
        allowed_obsolete = OBSOLETE_REFERENCE_ALLOWLIST.get(relative_path, frozenset())
        for reference in OBSOLETE_REFERENCES:
            offset = _obsolete_reference_offset(lowered, reference)
            if offset < 0 or reference in allowed_obsolete:
                continue
            findings.append(
                DocumentationFinding(
                    "DOC-STALE-001",
                    f"Obsolete documentation reference: {reference}",
                    f"{relative_path}:{_line_number(text, offset)}",
                )
            )
        if relative_path not in QUALITY_COMMAND_OWNERS:
            command = _VERIFICATION_COMMAND_PATTERN.search(text)
            if command is not None:
                findings.append(
                    DocumentationFinding(
                        "DOC-COMMAND-001",
                        "Verification commands must be owned by AGENTS.md, README.md, "
                        "or scripts/README.md.",
                        f"{relative_path}:{_line_number(text, command.start())}",
                    )
                )
        prose = _style_prose(text)
        text_without_fences = _CODE_FENCE_PATTERN.sub(
            lambda match: "\n" * match.group().count("\n"), text
        )
        for match in _INLINE_CODE_SPACING_PATTERN.finditer(text_without_fences):
            style_check_count += 1
            findings.append(
                DocumentationFinding(
                    "DOC-STYLE-002",
                    "Do not insert spaces between Japanese prose and inline code.",
                    f"{relative_path}:{_line_number(text_without_fences, match.start())}",
                )
            )
        for match in _JAPANESE_WORD_SPACING_PATTERN.finditer(prose):
            style_check_count += 1
            findings.append(
                DocumentationFinding(
                    "DOC-STYLE-003",
                    "Do not insert spaces between Japanese words.",
                    f"{relative_path}:{_line_number(prose, match.start())}",
                )
            )
        if style.get("sentence_style") == "plain":
            for match in _POLITE_SENTENCE_PATTERN.finditer(prose):
                style_check_count += 1
                findings.append(
                    DocumentationFinding(
                        "DOC-STYLE-001",
                        "Published documentation must use plain-form Japanese.",
                        f"{relative_path}:{_line_number(prose, match.start())}",
                    )
                )
        terms = style.get("terms", [])
        if not isinstance(terms, list):
            terms = []
        for term in terms:
            if not isinstance(term, dict):
                continue
            preferred = term.get("preferred")
            variants = term.get("variants")
            if not isinstance(preferred, str) or not isinstance(variants, list):
                continue
            for variant in variants:
                if not isinstance(variant, str):
                    continue
                pattern = re.compile(
                    rf"(?<![A-Za-z0-9_]){re.escape(variant)}(?![A-Za-z0-9_])",
                    re.IGNORECASE,
                )
                for match in pattern.finditer(prose):
                    style_check_count += 1
                    findings.append(
                        DocumentationFinding(
                            "DOC-TERM-001",
                            f"Use preferred documentation term: {preferred}",
                            f"{relative_path}:{_line_number(prose, match.start())}",
                        )
                    )

    return {
        "status": "failed" if findings else "passed",
        "metrics": {
            "published_page_count": len(source_paths),
            "label_count": len(labels),
            "automodule_count": len(automodules),
            "canonical_document_count": len(canonical_paths),
            "checked_reference_count": checked_reference_count,
            "style_check_count": style_check_count,
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


def _local_markdown_links(text: str) -> list[tuple[str, int]]:
    references: list[tuple[str, int]] = []
    for match in _MARKDOWN_LINK_PATTERN.finditer(text):
        target = match.group("target").strip().split("#", maxsplit=1)[0]
        if not target or target.startswith("#"):
            continue
        if re.match(r"^[a-z][a-z0-9+.-]*://", target, re.IGNORECASE):
            continue
        references.append((target.replace("\\", "/"), match.start("target")))
    return references


def _repository_path_references(text: str) -> list[tuple[str, int]]:
    references: list[tuple[str, int]] = []
    for match in _INLINE_CODE_PATTERN.finditer(text):
        value = match.group("value").strip().replace("\\", "/")
        if "<" in value or ">" in value or "*" in value:
            continue
        if _is_repository_path(value):
            references.append((value.rstrip("/"), match.start("value")))
    return references


def _is_repository_path(value: str) -> bool:
    return (
        value in _REPOSITORY_ROOT_FILES
        or value.startswith(_REPOSITORY_PATH_PREFIXES)
        or value.startswith(_PACKAGE_PATH_PREFIXES)
    )


def _repository_reference_target(reference: str) -> Path | None:
    if reference in _REPOSITORY_ROOT_FILES or reference.startswith(_REPOSITORY_PATH_PREFIXES):
        target = REPOSITORY_ROOT / reference
    elif reference.startswith(_PACKAGE_PATH_PREFIXES):
        target = REPOSITORY_ROOT / "src" / "werewolf_agent" / reference
    else:
        return None
    resolved = target.resolve()
    return resolved if _is_within_repository(resolved) else None


def _is_within_repository(path: Path) -> bool:
    try:
        path.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError:
        return False
    return True


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _obsolete_reference_offset(text: str, reference: str) -> int:
    if reference.isalpha():
        match = re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(reference)}(?![A-Za-z0-9_])",
            text,
        )
        return -1 if match is None else match.start()
    return text.find(reference)


def _style_configuration() -> dict[str, object]:
    with STYLE_PATH.open("rb") as stream:
        return tomllib.load(stream)


def _style_prose(text: str) -> str:
    prose = _CODE_FENCE_PATTERN.sub(lambda match: "\n" * match.group().count("\n"), text)
    prose = _SPHINX_LABEL_PATTERN.sub("", prose)
    prose = _INLINE_CODE_PATTERN_FOR_STYLE.sub("", prose)
    return _MARKDOWN_TARGET_PATTERN.sub("", prose)


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
