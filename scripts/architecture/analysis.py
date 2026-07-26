"""外部serviceを実行せずrepository architectureを解析・可視化する。"""

from __future__ import annotations

import argparse
import ast
import inspect
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from scripts._infra.artifacts import publish_directory, staged_directory
from scripts._infra.process import ARTIFACT_ROOT, REPOSITORY_ROOT
from scripts.architecture.definition import (
    ALLOWED_IMPORTS,
    ALLOWED_MODULE_IMPORTS,
    DEPENDENCY_EXCEPTION_REASONS,
    LAYERS,
    PUBLIC_MODULES,
)
from scripts.architecture.rendering import write_diagrams

PACKAGE_ROOT = REPOSITORY_ROOT / "src" / "werewolf_agent"
OUTPUT_ROOT = ARTIFACT_ROOT / "build" / "architecture"
SCHEMA_VERSION = 1


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


def module_name(path: Path) -> str:
    """Return the absolute project module name for a Python source path."""
    relative = path.relative_to(PACKAGE_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(("werewolf_agent", *parts))


def project_import_edges() -> list[ImportEdge]:
    """Return stable project import edges with relative source evidence."""
    modules = {module_name(path): path for path in sorted(PACKAGE_ROOT.rglob("*.py"))}
    edges: list[ImportEdge] = []
    for source_module, path in sorted(modules.items()):
        source_parts = source_module.split(".")
        source_layer = source_parts[1] if len(source_parts) > 1 else ""
        for imported, line in sorted(imports_with_lines(path, source_module)):
            target_module = _project_module_name(imported, modules)
            if target_module is None:
                continue
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
                imports.update(
                    (f"{resolved}.{alias.name}", node.lineno)
                    for alias in node.names
                    if alias.name != "*"
                )

    ImportVisitor().visit(tree)
    return imports


def _project_module_name(imported: str, modules: dict[str, Path]) -> str | None:
    """Imported symbolをrepository内で実在する最長moduleへ解決する。"""
    parts = imported.split(".")
    while parts and parts[0] == "werewolf_agent":
        candidate = ".".join(parts)
        if candidate in modules:
            return candidate
        parts.pop()
    return None


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
        module_import = (edge.source_module, edge.target_layer)
        if (
            edge.target_layer not in ALLOWED_IMPORTS[edge.source_layer]
            and module_import not in ALLOWED_MODULE_IMPORTS
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
                "source_module": source_module,
                "target_layer": target_layer,
                "reason": DEPENDENCY_EXCEPTION_REASONS[(source_module, target_layer)],
            }
            for source_module, target_layer in sorted(ALLOWED_MODULE_IMPORTS)
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
            "dependency_exception_count": len(ALLOWED_MODULE_IMPORTS),
            "finding_count": len(findings),
        },
        "findings": [asdict(finding) for finding in findings],
    }
    return document


def write_outputs(output_root: Path = OUTPUT_ROOT) -> dict[str, object]:
    """Generate architecture data, assessment, and diagrams."""
    if output_root != OUTPUT_ROOT:
        return _write_outputs(output_root)
    with staged_directory("architecture") as staging:
        document = _write_outputs(staging)
        if document["status"] == "passed":
            publish_directory(staging, output_root)
        return document


def _write_outputs(output_root: Path) -> dict[str, object]:
    """指定directoryへArchitecture成果物一式を書き出す。"""
    output_root.mkdir(parents=True, exist_ok=True)
    document = analyze()
    _write_json(output_root / "architecture.json", document)
    _write_json(output_root / "architecture.schema.json", architecture_schema())
    (output_root / "assessment.md").write_text(
        _assessment(document),
        encoding="utf-8",
    )
    write_diagrams(output_root, LAYERS, document.get("layer_edges"))
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
                "required": ["source_module", "target_layer", "reason"],
                "properties": {
                    "source_module": {"type": "string", "minLength": 1},
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
        f"- module 単位の依存例外: `{metrics['dependency_exception_count']}`",
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
                f"- `{exception['source_module']}` → "
                f"`{exception['target_layer']}`: {exception['reason']}"
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


if __name__ == "__main__":
    raise SystemExit(main())
