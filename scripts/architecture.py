"""Analyze and visualize repository architecture without executing external services."""

from __future__ import annotations

import argparse
import ast
import inspect
import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from html import escape
from pathlib import Path
from types import ModuleType
from typing import Any

import werewolf_agent.adapters as adapters
import werewolf_agent.agents as agents
import werewolf_agent.contracts as contracts
import werewolf_agent.domain as domain
import werewolf_agent.usecase as usecase
from scripts._support import ARTIFACT_ROOT, REPOSITORY_ROOT, remove_managed_path

PACKAGE_ROOT = REPOSITORY_ROOT / "src" / "werewolf_agent"
OUTPUT_ROOT = ARTIFACT_ROOT / "build" / "architecture"
SCHEMA_VERSION = 1

LAYERS = frozenset(
    {
        "adapters",
        "agents",
        "api",
        "configuration",
        "contracts",
        "domain",
        "interfaces",
        "observability",
        "resources",
        "security",
        "usecase",
    }
)

ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    "domain": frozenset({"domain"}),
    "configuration": frozenset({"configuration"}),
    "contracts": frozenset({"configuration", "contracts", "security"}),
    "security": frozenset({"configuration", "contracts", "security"}),
    "observability": frozenset({"configuration", "contracts", "observability", "security"}),
    "agents": frozenset({"agents", "configuration", "contracts"}),
    "usecase": frozenset({"configuration", "contracts", "domain", "usecase"}),
    "adapters": frozenset(
        {
            "adapters",
            "agents",
            "configuration",
            "contracts",
            "domain",
            "observability",
            "security",
            "usecase",
        }
    ),
    "api": frozenset({"api", "configuration", "contracts", "observability", "security", "usecase"}),
    "interfaces": frozenset(
        {
            "adapters",
            "agents",
            "configuration",
            "contracts",
            "interfaces",
            "observability",
            "security",
            "usecase",
        }
    ),
    "resources": frozenset({"resources"}),
}

DEPENDENCY_EXCEPTION_REASONS = {
    ("src/werewolf_agent/api/bootstrap.py", "adapters"): (
        "HTTP composition root が adapter 実装を構築する。"
    ),
}
ALLOWED_PATH_IMPORTS = frozenset(DEPENDENCY_EXCEPTION_REASONS)

PUBLIC_MODULES: tuple[ModuleType, ...] = (domain, usecase, contracts, agents, adapters)


@dataclass(frozen=True, slots=True)
class ImportEdge:
    """One project import with source evidence."""

    source_module: str
    target_module: str
    source_layer: str
    target_layer: str
    path: str
    line: int


@dataclass(frozen=True, slots=True)
class Finding:
    """One actionable architecture violation."""

    rule_id: str
    severity: str
    message: str
    evidence: dict[str, object]


@dataclass(frozen=True, slots=True)
class DiagramNode:
    """One node in a generated architecture diagram."""

    node_id: str
    label: str
    group: str


@dataclass(frozen=True, slots=True)
class DiagramEdge:
    """One directed relation in a generated architecture diagram."""

    source: str
    target: str
    label: str = ""


SYSTEM_NODES = (
    DiagramNode("react", "React", "interface"),
    DiagramNode("streamlit", "Streamlit", "interface"),
    DiagramNode("cli", "CLI", "interface"),
    DiagramNode("administrator", "Administrator", "interface"),
    DiagramNode("api", "HTTP API", "application"),
    DiagramNode("worker", "Worker", "application"),
    DiagramNode("usecase", "GameApplication", "core"),
    DiagramNode("domain", "Domain", "core"),
    DiagramNode("agents", "Agents", "core"),
    DiagramNode("supabase", "Supabase", "external"),
    DiagramNode("llm", "LLM Provider", "external"),
)
SYSTEM_EDGES = (
    DiagramEdge("react", "api", "HTTP"),
    DiagramEdge("streamlit", "api", "HTTP"),
    DiagramEdge("cli", "api", "HTTP"),
    DiagramEdge("administrator", "api", "Privileged HTTP"),
    DiagramEdge("api", "usecase"),
    DiagramEdge("api", "supabase", "Auth / DB"),
    DiagramEdge("worker", "usecase"),
    DiagramEdge("worker", "supabase", "Queue / DB"),
    DiagramEdge("worker", "agents"),
    DiagramEdge("agents", "llm"),
    DiagramEdge("usecase", "domain"),
)
SYSTEM_POSITIONS = {
    "react": (50, 50),
    "streamlit": (50, 144),
    "cli": (50, 238),
    "administrator": (50, 332),
    "api": (320, 144),
    "worker": (320, 332),
    "usecase": (590, 238),
    "domain": (860, 238),
    "agents": (590, 426),
    "supabase": (860, 50),
    "llm": (860, 426),
}

DOMAIN_NODES = (
    DiagramNode("game", "Game", "aggregate"),
    DiagramNode("state", "GameState", "value"),
    DiagramNode("events", "GameEvent", "value"),
    DiagramNode("ruleset", "RuleSet", "policy"),
    DiagramNode("registry", "RuleRegistry", "policy"),
    DiagramNode("definition", "RuleSetDefinition", "configuration"),
    DiagramNode("action", "ActionPolicy", "policy"),
    DiagramNode("resolution", "ResolutionPolicy", "policy"),
    DiagramNode("phase", "PhasePolicy", "policy"),
    DiagramNode("victory", "VictoryPolicy", "policy"),
    DiagramNode("visibility", "VisibilityPolicy", "policy"),
)
DOMAIN_EDGES = (
    DiagramEdge("game", "state", "owns"),
    DiagramEdge("game", "events", "emits"),
    DiagramEdge("game", "ruleset", "uses"),
    DiagramEdge("registry", "definition", "validates"),
    DiagramEdge("registry", "ruleset", "builds"),
    DiagramEdge("ruleset", "action"),
    DiagramEdge("ruleset", "resolution"),
    DiagramEdge("ruleset", "phase"),
    DiagramEdge("ruleset", "victory"),
    DiagramEdge("ruleset", "visibility"),
)
DOMAIN_POSITIONS = {
    "game": (50, 50),
    "registry": (860, 50),
    "state": (50, 194),
    "events": (320, 194),
    "ruleset": (590, 194),
    "definition": (860, 194),
    "action": (50, 338),
    "resolution": (260, 338),
    "phase": (470, 338),
    "victory": (680, 338),
    "visibility": (890, 338),
}


def module_name(path: Path) -> str:
    """Return the absolute project module name for a Python source path."""
    relative = path.relative_to(PACKAGE_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(("werewolf_agent", *parts))


def project_import_edges() -> list[ImportEdge]:
    """Return stable project import edges with relative source evidence."""
    edges: list[ImportEdge] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        source_module = module_name(path)
        source_parts = source_module.split(".")
        source_layer = source_parts[1] if len(source_parts) > 1 else ""
        for target_module, line in imports_with_lines(path, source_module):
            parts = target_module.split(".")
            if len(parts) < 2 or parts[0] != "werewolf_agent":
                continue
            target_layer = parts[1]
            if source_layer not in LAYERS or target_layer not in LAYERS:
                continue
            edges.append(
                ImportEdge(
                    source_module=source_module,
                    target_module=target_module,
                    source_layer=source_layer,
                    target_layer=target_layer,
                    path=path.relative_to(REPOSITORY_ROOT).as_posix(),
                    line=line,
                )
            )
    return sorted(
        set(edges),
        key=lambda edge: (
            edge.source_module,
            edge.target_module,
            edge.path,
            edge.line,
        ),
    )


def imports_with_lines(path: Path, source_module: str) -> set[tuple[str, int]]:
    """Parse runtime imports while excluding type-checking-only branches."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[tuple[str, int]] = set()

    class ImportVisitor(ast.NodeVisitor):
        def visit_If(self, node: ast.If) -> None:
            if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
                for child in node.orelse:
                    self.visit(child)
                return
            self.generic_visit(node)

        def visit_Import(self, node: ast.Import) -> None:
            imports.update((alias.name, node.lineno) for alias in node.names)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            resolved = _resolve_import_from(
                source_module,
                node,
                is_package=path.name == "__init__.py",
            )
            if resolved:
                imports.add((resolved, node.lineno))
                if node.module is None or resolved == "werewolf_agent":
                    imports.update(
                        (f"{resolved}.{alias.name}", node.lineno)
                        for alias in node.names
                        if alias.name != "*"
                    )

    ImportVisitor().visit(tree)
    return imports


def graph_cycles(graph: dict[str, set[str]]) -> list[tuple[str, ...]]:
    """Return canonical directed cycles from a graph."""
    found: set[tuple[str, ...]] = set()

    def visit(node: str, path: tuple[str, ...]) -> None:
        if node in path:
            cycle = path[path.index(node) :]
            rotations = [cycle[index:] + cycle[:index] for index in range(len(cycle))]
            found.add(min(rotations))
            return
        for target in sorted(graph.get(node, set())):
            visit(target, (*path, node))

    for node in sorted(graph):
        visit(node, ())
    return sorted(found)


def analyze() -> dict[str, object]:
    """Build the complete deterministic architecture analysis document."""
    edges = project_import_edges()
    layer_graph: dict[str, set[str]] = {layer: set() for layer in sorted(LAYERS)}
    modules = {module_name(path): path for path in sorted(PACKAGE_ROOT.rglob("*.py"))}
    module_graph: dict[str, set[str]] = {module: set() for module in sorted(modules)}
    findings: list[Finding] = []

    for layer in sorted(LAYERS):
        if not (PACKAGE_ROOT / layer).is_dir():
            findings.append(
                Finding(
                    "ARCH-LAYER-001",
                    "error",
                    f"Required layer is missing: {layer}",
                    {"layer": layer},
                )
            )

    for edge in edges:
        if edge.source_layer != edge.target_layer:
            layer_graph[edge.source_layer].add(edge.target_layer)
        if edge.target_module in module_graph and edge.source_module != edge.target_module:
            module_graph[edge.source_module].add(edge.target_module)
        path_import = (edge.path, edge.target_layer)
        if (
            edge.target_layer not in ALLOWED_IMPORTS[edge.source_layer]
            and path_import not in ALLOWED_PATH_IMPORTS
        ):
            findings.append(
                Finding(
                    "ARCH-DEPENDENCY-001",
                    "error",
                    f"{edge.source_layer} cannot import {edge.target_layer}",
                    {
                        "path": edge.path,
                        "line": edge.line,
                        "source_module": edge.source_module,
                        "target_module": edge.target_module,
                    },
                )
            )

    layer_cycles = graph_cycles(layer_graph)
    module_cycles = graph_cycles(module_graph)
    for cycle in layer_cycles:
        findings.append(
            Finding(
                "ARCH-CYCLE-001",
                "error",
                "Layer dependency cycle detected.",
                {"cycle": list(cycle)},
            )
        )
    for cycle in module_cycles:
        findings.append(
            Finding(
                "ARCH-CYCLE-002",
                "error",
                "Module dependency cycle detected.",
                {"cycle": list(cycle)},
            )
        )

    findings.extend(_public_docstring_findings())
    layer_metrics = _layer_metrics(layer_graph)
    public_symbols = {
        module.__name__: sorted(str(name) for name in getattr(module, "__all__", ()))
        for module in PUBLIC_MODULES
    }

    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "status": "failed" if findings else "passed",
        "layers": [
            {
                "id": layer,
                "path": f"src/werewolf_agent/{layer}",
                "allowed_imports": sorted(ALLOWED_IMPORTS[layer]),
                "metrics": layer_metrics[layer],
            }
            for layer in sorted(LAYERS)
        ],
        "layer_edges": [
            {"source": source, "target": target}
            for source in sorted(layer_graph)
            for target in sorted(layer_graph[source])
        ],
        "dependency_exceptions": [
            {
                "path": path,
                "target_layer": target_layer,
                "reason": DEPENDENCY_EXCEPTION_REASONS[(path, target_layer)],
            }
            for path, target_layer in sorted(ALLOWED_PATH_IMPORTS)
        ],
        "modules": [
            {
                "id": module,
                "path": modules[module].relative_to(REPOSITORY_ROOT).as_posix(),
                "imports": sorted(module_graph[module]),
            }
            for module in sorted(modules)
        ],
        "import_evidence": [asdict(edge) for edge in edges],
        "public_symbols": public_symbols,
        "metrics": {
            "layer_count": len(LAYERS),
            "module_count": len(modules),
            "cross_layer_edge_count": sum(len(targets) for targets in layer_graph.values()),
            "dependency_exception_count": len(ALLOWED_PATH_IMPORTS),
            "finding_count": len(findings),
        },
        "findings": [asdict(finding) for finding in findings],
    }
    return document


def write_outputs(output_root: Path = OUTPUT_ROOT) -> dict[str, object]:
    """Generate architecture data, assessment, and diagrams."""
    if output_root == OUTPUT_ROOT and output_root.exists():
        remove_managed_path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    document = analyze()
    _write_json(output_root / "architecture.json", document)
    _write_json(output_root / "architecture.schema.json", architecture_schema())
    (output_root / "assessment.md").write_text(
        _assessment(document),
        encoding="utf-8",
    )
    _write_svg(
        output_root / "system-context.svg",
        "System context",
        SYSTEM_NODES,
        SYSTEM_EDGES,
        positions=SYSTEM_POSITIONS,
    )
    layer_nodes = tuple(DiagramNode(layer, layer, "layer") for layer in sorted(LAYERS))
    raw_layer_edges = document.get("layer_edges")
    if not isinstance(raw_layer_edges, list):
        raise TypeError("Architecture analysis did not return layer_edges.")
    layer_edges = tuple(
        DiagramEdge(str(edge["source"]), str(edge["target"]))
        for edge in raw_layer_edges
        if isinstance(edge, dict)
    )
    _write_svg(
        output_root / "layer-dependencies.svg",
        "Python layer dependencies",
        layer_nodes,
        layer_edges,
        positions=_circular_positions(layer_nodes),
    )
    _write_svg(
        output_root / "domain-structure.svg",
        "Domain structure",
        DOMAIN_NODES,
        DOMAIN_EDGES,
        positions=DOMAIN_POSITIONS,
    )
    return document


def architecture_schema() -> dict[str, object]:
    """Return the public JSON Schema for architecture analysis."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://werewolf-agent.local/schema/architecture.json",
        "title": "Werewolf Agent Architecture Analysis",
        "type": "object",
        "required": [
            "schema_version",
            "status",
            "layers",
            "layer_edges",
            "dependency_exceptions",
            "modules",
            "import_evidence",
            "public_symbols",
            "metrics",
            "findings",
        ],
        "$defs": {
            "coupling_metrics": {
                "type": "object",
                "required": [
                    "afferent_coupling",
                    "efferent_coupling",
                    "instability",
                ],
                "properties": {
                    "afferent_coupling": {"type": "integer", "minimum": 0},
                    "efferent_coupling": {"type": "integer", "minimum": 0},
                    "instability": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "additionalProperties": False,
            },
            "layer": {
                "type": "object",
                "required": ["id", "path", "allowed_imports", "metrics"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "path": {"type": "string", "minLength": 1},
                    "allowed_imports": {
                        "type": "array",
                        "items": {"type": "string"},
                        "uniqueItems": True,
                    },
                    "metrics": {"$ref": "#/$defs/coupling_metrics"},
                },
                "additionalProperties": False,
            },
            "edge": {
                "type": "object",
                "required": ["source", "target"],
                "properties": {
                    "source": {"type": "string", "minLength": 1},
                    "target": {"type": "string", "minLength": 1},
                },
                "additionalProperties": False,
            },
            "module": {
                "type": "object",
                "required": ["id", "path", "imports"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "path": {"type": "string", "minLength": 1},
                    "imports": {
                        "type": "array",
                        "items": {"type": "string"},
                        "uniqueItems": True,
                    },
                },
                "additionalProperties": False,
            },
            "import_evidence": {
                "type": "object",
                "required": [
                    "source_module",
                    "target_module",
                    "source_layer",
                    "target_layer",
                    "path",
                    "line",
                ],
                "properties": {
                    "source_module": {"type": "string", "minLength": 1},
                    "target_module": {"type": "string", "minLength": 1},
                    "source_layer": {"type": "string", "minLength": 1},
                    "target_layer": {"type": "string", "minLength": 1},
                    "path": {"type": "string", "minLength": 1},
                    "line": {"type": "integer", "minimum": 1},
                },
                "additionalProperties": False,
            },
            "finding": {
                "type": "object",
                "required": ["rule_id", "severity", "message", "evidence"],
                "properties": {
                    "rule_id": {"type": "string", "minLength": 1},
                    "severity": {"enum": ["error", "warning"]},
                    "message": {"type": "string", "minLength": 1},
                    "evidence": {"type": "object"},
                },
                "additionalProperties": False,
            },
            "dependency_exception": {
                "type": "object",
                "required": ["path", "target_layer", "reason"],
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "target_layer": {"type": "string", "minLength": 1},
                    "reason": {"type": "string", "minLength": 1},
                },
                "additionalProperties": False,
            },
        },
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "status": {"enum": ["passed", "failed"]},
            "layers": {"type": "array", "items": {"$ref": "#/$defs/layer"}},
            "layer_edges": {"type": "array", "items": {"$ref": "#/$defs/edge"}},
            "dependency_exceptions": {
                "type": "array",
                "items": {"$ref": "#/$defs/dependency_exception"},
            },
            "modules": {"type": "array", "items": {"$ref": "#/$defs/module"}},
            "import_evidence": {
                "type": "array",
                "items": {"$ref": "#/$defs/import_evidence"},
            },
            "public_symbols": {
                "type": "object",
                "additionalProperties": {
                    "type": "array",
                    "items": {"type": "string"},
                    "uniqueItems": True,
                },
            },
            "metrics": {
                "type": "object",
                "required": [
                    "layer_count",
                    "module_count",
                    "cross_layer_edge_count",
                    "dependency_exception_count",
                    "finding_count",
                ],
                "properties": {
                    "layer_count": {"type": "integer", "minimum": 0},
                    "module_count": {"type": "integer", "minimum": 0},
                    "cross_layer_edge_count": {"type": "integer", "minimum": 0},
                    "dependency_exception_count": {"type": "integer", "minimum": 0},
                    "finding_count": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": False,
            },
            "findings": {
                "type": "array",
                "items": {"$ref": "#/$defs/finding"},
            },
        },
        "additionalProperties": False,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the architecture command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Generate architecture artifacts and return their evaluation status."""
    arguments = build_parser().parse_args(argv)
    document = write_outputs(arguments.output)
    print(arguments.output / "assessment.md")
    return 0 if document["status"] == "passed" else 1


def _resolve_import_from(
    source_module: str,
    node: ast.ImportFrom,
    *,
    is_package: bool,
) -> str:
    if node.level == 0:
        return node.module or ""
    source_parts = source_module.split(".")
    if not is_package:
        source_parts = source_parts[:-1]
    keep = max(0, len(source_parts) - node.level + 1)
    base = source_parts[:keep]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


def _public_docstring_findings() -> list[Finding]:
    findings: list[Finding] = []
    for module in PUBLIC_MODULES:
        if not inspect.getdoc(module):
            findings.append(
                Finding(
                    "ARCH-DOCSTRING-001",
                    "error",
                    f"Public module has no docstring: {module.__name__}",
                    {"module": module.__name__},
                )
            )
        exports = getattr(module, "__all__", None)
        if not isinstance(exports, list):
            findings.append(
                Finding(
                    "ARCH-PUBLIC-001",
                    "error",
                    f"Public module must define __all__ as a list: {module.__name__}",
                    {"module": module.__name__},
                )
            )
            continue
        for name in exports:
            value = getattr(module, name, None)
            if value is None:
                findings.append(
                    Finding(
                        "ARCH-PUBLIC-002",
                        "error",
                        f"Export does not exist: {module.__name__}.{name}",
                        {"module": module.__name__, "symbol": name},
                    )
                )
                continue
            if not (inspect.isclass(value) or inspect.isfunction(value)):
                continue
            if not inspect.getdoc(value):
                findings.append(
                    Finding(
                        "ARCH-DOCSTRING-002",
                        "error",
                        f"Public symbol has no docstring: {module.__name__}.{name}",
                        {"module": module.__name__, "symbol": name},
                    )
                )
            if inspect.isclass(value):
                findings.extend(_class_docstring_findings(module, name, value))
    return findings


def _class_docstring_findings(
    module: ModuleType,
    exported_name: str,
    value: type[Any],
) -> list[Finding]:
    findings: list[Finding] = []
    for name, member in vars(value).items():
        if name.startswith("_"):
            continue
        documented = member
        if isinstance(member, (classmethod, staticmethod)):
            documented = member.__func__
        elif isinstance(member, property):
            documented = member.fget
        if documented is None or not (
            inspect.isfunction(documented)
            or inspect.ismethod(documented)
            or isinstance(member, property)
        ):
            continue
        if inspect.getdoc(documented):
            continue
        findings.append(
            Finding(
                "ARCH-DOCSTRING-003",
                "error",
                f"Public member has no docstring: {module.__name__}.{exported_name}.{name}",
                {
                    "module": module.__name__,
                    "symbol": exported_name,
                    "member": name,
                },
            )
        )
    return findings


def _layer_metrics(graph: dict[str, set[str]]) -> dict[str, dict[str, object]]:
    incoming: dict[str, set[str]] = {layer: set() for layer in graph}
    for source, targets in graph.items():
        for target in targets:
            incoming[target].add(source)
    metrics: dict[str, dict[str, object]] = {}
    for layer in sorted(graph):
        efferent = len(graph[layer])
        afferent = len(incoming[layer])
        denominator = afferent + efferent
        metrics[layer] = {
            "afferent_coupling": afferent,
            "efferent_coupling": efferent,
            "instability": round(efferent / denominator, 4) if denominator else 0.0,
        }
    return metrics


def _assessment(document: dict[str, object]) -> str:
    findings = document["findings"]
    metrics = document["metrics"]
    layers = document["layers"]
    dependency_exceptions = document["dependency_exceptions"]
    assert isinstance(findings, list)
    assert isinstance(metrics, dict)
    assert isinstance(layers, list)
    assert isinstance(dependency_exceptions, list)
    lines = [
        "# アーキテクチャ評価",
        "",
        f"- 判定: `{document['status']}`",
        f"- layer: `{metrics['layer_count']}`",
        f"- module: `{metrics['module_count']}`",
        f"- layer 間の依存: `{metrics['cross_layer_edge_count']}`",
        f"- path 単位の依存例外: `{metrics['dependency_exception_count']}`",
        f"- 検出事項: `{len(findings)}`",
        "",
        "必須 layer、許可された依存方向、循環、公開 API、docstring を判定対象とする。",
        "",
        "## 結合度",
        "",
        "| layer | 求心結合 Ca | 遠心結合 Ce | 不安定度 I |",
        "| --- | ---: | ---: | ---: |",
    ]
    for layer in layers:
        assert isinstance(layer, dict)
        coupling = layer["metrics"]
        assert isinstance(coupling, dict)
        lines.append(
            f"| `{layer['id']}` | {coupling['afferent_coupling']} | "
            f"{coupling['efferent_coupling']} | {coupling['instability']} |"
        )
    lines.extend(
        [
            "",
            "不安定度は `Ce / (Ca + Ce)` で表す。値そのものを合否条件にはせず、"
            "変更影響を調べる入口として使う。",
            "",
        ]
    )
    lines.extend(["## 依存例外", ""])
    if dependency_exceptions:
        for exception in dependency_exceptions:
            assert isinstance(exception, dict)
            lines.append(
                f"- `{exception['path']}` → `{exception['target_layer']}`: {exception['reason']}"
            )
    else:
        lines.append("path 単位の依存例外はない。")
    lines.append("")
    if not findings:
        lines.extend(["## 検出事項", "", "アーキテクチャ違反は検出されなかった。", ""])
        return "\n".join(lines)
    lines.extend(["## 検出事項", ""])
    for finding in findings:
        assert isinstance(finding, dict)
        lines.append(
            f"- `{finding['rule_id']}` {finding['message']} "
            f"`{json.dumps(finding['evidence'], ensure_ascii=False, sort_keys=True)}`"
        )
    lines.append("")
    return "\n".join(lines)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_svg(
    path: Path,
    title: str,
    nodes: tuple[DiagramNode, ...],
    edges: tuple[DiagramEdge, ...],
    *,
    positions: dict[str, tuple[int, int]] | None = None,
) -> None:
    columns = max(2, math.ceil(math.sqrt(len(nodes))))
    box_width = 180
    box_height = 64
    gap_x = 90
    gap_y = 80
    margin = 50
    if positions is None:
        positions = {}
        for index, node in enumerate(nodes):
            row, column = divmod(index, columns)
            positions[node.node_id] = (
                margin + column * (box_width + gap_x),
                margin + row * (box_height + gap_y),
            )
    node_ids = {node.node_id for node in nodes}
    if positions.keys() != node_ids:
        raise ValueError("Diagram positions must match diagram nodes.")
    width = max(x for x, _ in positions.values()) + box_width + margin
    height = max(y for _, y in positions.values()) + box_height + margin
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-labelledby="title desc">',
        f'<title id="title">{escape(title)}</title>',
        (
            f'<desc id="desc">{escape(title)} generated from the repository '
            "architecture model.</desc>"
        ),
        '<defs><marker id="arrow" markerWidth="10" markerHeight="7" '
        'refX="9" refY="3.5" orient="auto">'
        '<polygon points="0 0, 10 3.5, 0 7" fill="#52606d"/>'
        "</marker></defs>",
    ]
    for edge in edges:
        if edge.source not in positions or edge.target not in positions:
            continue
        x1, y1, x2, y2 = _edge_endpoints(
            positions[edge.source],
            positions[edge.target],
            box_width=box_width,
            box_height=box_height,
        )
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            'stroke="#52606d" stroke-width="1.5" marker-end="url(#arrow)"/>'
        )
        if edge.label:
            parts.append(
                f'<text x="{(x1 + x2) / 2}" y="{(y1 + y2) / 2 - 5}" '
                'font-family="sans-serif" font-size="11" text-anchor="middle" '
                f'fill="#334e68">{escape(edge.label)}</text>'
            )
    colors = {
        "aggregate": "#d9eafd",
        "application": "#e6f6ff",
        "configuration": "#fff3c4",
        "core": "#d9eafd",
        "external": "#f5e1f7",
        "interface": "#e3f9e5",
        "layer": "#e6f6ff",
        "policy": "#fff3c4",
        "value": "#f0f4f8",
    }
    for node in nodes:
        x, y = positions[node.node_id]
        fill = colors.get(node.group, "#f0f4f8")
        parts.extend(
            [
                f'<rect x="{x}" y="{y}" width="{box_width}" height="{box_height}" '
                f'rx="8" fill="{fill}" stroke="#334e68" stroke-width="1.5"/>',
                f'<text x="{x + box_width / 2}" y="{y + box_height / 2 + 5}" '
                'font-family="sans-serif" font-size="14" font-weight="600" '
                f'text-anchor="middle" fill="#102a43">{escape(node.label)}</text>',
            ]
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def _circular_positions(nodes: tuple[DiagramNode, ...]) -> dict[str, tuple[int, int]]:
    center_x = 430
    center_y = 350
    radius_x = 340
    radius_y = 270
    positions: dict[str, tuple[int, int]] = {}
    for index, node in enumerate(nodes):
        angle = -math.pi / 2 + 2 * math.pi * index / len(nodes)
        positions[node.node_id] = (
            round(center_x + radius_x * math.cos(angle) - 90),
            round(center_y + radius_y * math.sin(angle) - 32),
        )
    return positions


def _edge_endpoints(
    source: tuple[int, int],
    target: tuple[int, int],
    *,
    box_width: int,
    box_height: int,
) -> tuple[float, float, float, float]:
    source_center = (source[0] + box_width / 2, source[1] + box_height / 2)
    target_center = (target[0] + box_width / 2, target[1] + box_height / 2)
    delta_x = target_center[0] - source_center[0]
    delta_y = target_center[1] - source_center[1]
    if delta_x == 0 and delta_y == 0:
        return (*source_center, *target_center)
    scale = 1 / max(
        abs(delta_x) / (box_width / 2),
        abs(delta_y) / (box_height / 2),
    )
    offset_x = delta_x * scale
    offset_y = delta_y * scale
    return (
        source_center[0] + offset_x,
        source_center[1] + offset_y,
        target_center[0] - offset_x,
        target_center[1] - offset_y,
    )


if __name__ == "__main__":
    raise SystemExit(main())
