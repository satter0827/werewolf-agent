"""Architecture定義からSVG図を生成する。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from html import escape
from pathlib import Path


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


def write_diagrams(
    output_root: Path,
    layer_ids: frozenset[str],
    raw_layer_edges: object,
) -> None:
    """System、layer、domainのSVGを同じ構造定義から生成する。"""
    _write_svg(
        output_root / "system-context.svg",
        "System context",
        SYSTEM_NODES,
        SYSTEM_EDGES,
        positions=SYSTEM_POSITIONS,
    )
    layer_nodes = tuple(DiagramNode(layer, layer, "layer") for layer in sorted(layer_ids))
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


__all__ = ["write_diagrams"]
