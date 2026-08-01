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


@dataclass(frozen=True, slots=True)
class DiagramSpec:
    """One deterministic architecture diagram definition."""

    filename: str
    title: str
    description: str
    nodes: tuple[DiagramNode, ...]
    edges: tuple[DiagramEdge, ...]
    positions: dict[str, tuple[int, int]]


STATIC_DIAGRAMS = (
    DiagramSpec(
        "system-context.svg",
        "Werewolf Agent system context",
        "利用者と外部サービスから見たWerewolf Agentの接続関係。",
        (
            DiagramNode("player", "Player / Observer", "actor"),
            DiagramNode("administrator", "Administrator", "actor"),
            DiagramNode("developer", "Python SDK User", "actor"),
            DiagramNode("system", "Werewolf Agent", "system"),
            DiagramNode("supabase", "Supabase", "external"),
            DiagramNode("llm", "LLM Provider", "external"),
            DiagramNode("artifacts", "Local Artifacts", "external"),
        ),
        (
            DiagramEdge("player", "system", "Play / Observe"),
            DiagramEdge("administrator", "system", "Operate"),
            DiagramEdge("developer", "system", "Python API"),
            DiagramEdge("system", "supabase", "Auth / Data / Queue"),
            DiagramEdge("system", "llm", "Decision"),
            DiagramEdge("system", "artifacts", "Experiment / Quality"),
        ),
        {
            "player": (50, 50),
            "administrator": (50, 194),
            "developer": (50, 338),
            "system": (430, 194),
            "supabase": (810, 50),
            "llm": (810, 194),
            "artifacts": (810, 338),
        },
    ),
    DiagramSpec(
        "runtime-processes.svg",
        "Runtime processes",
        "CLI、Streamlit、API、workerと内部実行境界の接続関係。",
        (
            DiagramNode("streamlit", "Streamlit", "interface"),
            DiagramNode("cli", "CLI", "interface"),
            DiagramNode("api", "API Process", "process"),
            DiagramNode("worker", "Worker Process", "process"),
            DiagramNode("application", "Application", "core"),
            DiagramNode("simulation", "Simulation", "core"),
            DiagramNode("domain", "Domain", "core"),
            DiagramNode("agents", "Agents", "core"),
            DiagramNode("supabase", "Supabase", "external"),
            DiagramNode("llm_adapter", "LLM Adapter", "adapter"),
            DiagramNode("llm", "LLM Provider", "external"),
        ),
        (
            DiagramEdge("streamlit", "api", "HTTP"),
            DiagramEdge("cli", "api", "HTTP"),
            DiagramEdge("api", "application", "Use case"),
            DiagramEdge("api", "supabase", "Auth / Queue"),
            DiagramEdge("supabase", "worker", "Claim"),
            DiagramEdge("worker", "application", "Prepare / Commit"),
            DiagramEdge("worker", "simulation", "Run"),
            DiagramEdge("simulation", "domain", "Mutate via Game"),
            DiagramEdge("simulation", "agents", "Decide"),
            DiagramEdge("agents", "llm_adapter", "Port"),
            DiagramEdge("llm_adapter", "llm", "Provider API"),
        ),
        {
            "streamlit": (50, 50),
            "cli": (50, 194),
            "api": (320, 122),
            "supabase": (590, 50),
            "worker": (590, 194),
            "application": (860, 50),
            "simulation": (860, 194),
            "domain": (1130, 50),
            "agents": (1130, 194),
            "llm_adapter": (1130, 338),
            "llm": (860, 338),
        },
    ),
    DiagramSpec(
        "public-sdk.svg",
        "Public Python SDK",
        "公開Pythonモジュールの責務と依存方向。",
        (
            DiagramNode("setup", "setup", "public"),
            DiagramNode("domain", "domain", "public"),
            DiagramNode("agents", "agents", "public"),
            DiagramNode("simulation", "simulation", "public"),
            DiagramNode("experiments", "experiments", "public"),
            DiagramNode("application", "application", "public"),
        ),
        (
            DiagramEdge("setup", "domain"),
            DiagramEdge("simulation", "setup"),
            DiagramEdge("simulation", "domain"),
            DiagramEdge("simulation", "agents"),
            DiagramEdge("experiments", "simulation"),
            DiagramEdge("experiments", "setup"),
            DiagramEdge("experiments", "domain"),
            DiagramEdge("experiments", "agents"),
            DiagramEdge("application", "setup"),
            DiagramEdge("application", "domain"),
        ),
        {
            "experiments": (50, 50),
            "simulation": (320, 50),
            "application": (50, 194),
            "agents": (590, 50),
            "setup": (320, 194),
            "domain": (590, 194),
        },
    ),
    DiagramSpec(
        "domain-structure.svg",
        "Domain structure",
        "Rule定義から構築した規則をGameが状態遷移へ適用する関係。",
        (
            DiagramNode("game", "Game", "aggregate"),
            DiagramNode("state", "GameState", "value"),
            DiagramNode("events", "GameEvent", "value"),
            DiagramNode("ruleset", "CompiledRuleSet", "definition"),
            DiagramNode("definition", "RuleSetDefinition", "definition"),
            DiagramNode("factory", "build_game_rules", "factory"),
            DiagramNode("engine", "Rule Engine", "module"),
        ),
        (
            DiagramEdge("game", "state", "Owns"),
            DiagramEdge("game", "events", "Emits"),
            DiagramEdge("game", "ruleset", "Uses"),
            DiagramEdge("definition", "factory", "Input"),
            DiagramEdge("factory", "ruleset", "Builds"),
            DiagramEdge("game", "engine", "Calls"),
        ),
        {
            "game": (50, 50),
            "engine": (320, 50),
            "ruleset": (590, 50),
            "factory": (860, 50),
            "state": (50, 194),
            "events": (320, 194),
            "definition": (860, 194),
        },
    ),
    DiagramSpec(
        "game-lifecycle.svg",
        "Game lifecycle",
        "Gameが保持するphaseの遷移と終了判定。",
        (
            DiagramNode("setup", "setup", "state"),
            DiagramNode("night", "night", "state"),
            DiagramNode("discussion", "day_discussion", "state"),
            DiagramNode("voting", "voting", "state"),
            DiagramNode("finished", "finished", "terminal"),
        ),
        (
            DiagramEdge("setup", "night", "Night first"),
            DiagramEdge("setup", "discussion", "Day first"),
            DiagramEdge("night", "discussion"),
            DiagramEdge("discussion", "voting"),
            DiagramEdge("voting", "night", "Next day"),
            DiagramEdge("night", "finished", "Victory"),
            DiagramEdge("voting", "finished", "Victory"),
        ),
        {
            "setup": (50, 122),
            "night": (320, 50),
            "discussion": (590, 50),
            "voting": (860, 50),
            "finished": (590, 194),
        },
    ),
    DiagramSpec(
        "setup-resolution.svg",
        "Game setup resolution",
        "template、保存revision、inline documentを正規化して一局へ固定する流れ。",
        (
            DiagramNode("template", "Bundled Template", "source"),
            DiagramNode("revision", "Saved Revision", "source"),
            DiagramNode("inline", "Inline Document", "source"),
            DiagramNode("validate", "Validate", "process"),
            DiagramNode("normalize", "Normalize / Generate", "process"),
            DiagramNode("command", "CreateGameCommand", "value"),
            DiagramNode("game", "Game + Rule Pack", "aggregate"),
        ),
        (
            DiagramEdge("template", "validate"),
            DiagramEdge("revision", "validate"),
            DiagramEdge("inline", "validate"),
            DiagramEdge("validate", "normalize", "Meaning"),
            DiagramEdge("normalize", "command", "Seed / Roster / Checksum"),
            DiagramEdge("command", "game", "Create"),
        ),
        {
            "template": (50, 50),
            "revision": (50, 194),
            "inline": (50, 338),
            "validate": (320, 194),
            "normalize": (590, 194),
            "command": (860, 194),
            "game": (1130, 194),
        },
    ),
    DiagramSpec(
        "request-lifecycle.svg",
        "Asynchronous request lifecycle",
        "HTTP requestを認可してqueueへ保存し、workerが計算結果をcommitする流れ。",
        (
            DiagramNode("client", "Client", "actor"),
            DiagramNode("route", "API Route", "interface"),
            DiagramNode("authorize", "Application", "core"),
            DiagramNode("queue", "Operation Queue", "external"),
            DiagramNode("worker", "Worker", "process"),
            DiagramNode("compute", "Domain / Simulation", "core"),
            DiagramNode("commit", "Application Commit", "core"),
            DiagramNode("result", "Operation Result", "value"),
        ),
        (
            DiagramEdge("client", "route", "Request"),
            DiagramEdge("route", "authorize", "Wire to command"),
            DiagramEdge("authorize", "queue", "Authorized input"),
            DiagramEdge("queue", "worker", "Claim"),
            DiagramEdge("worker", "compute", "Execute"),
            DiagramEdge("compute", "commit", "Computed transition"),
            DiagramEdge("commit", "result", "Atomic save"),
            DiagramEdge("result", "client", "Poll"),
        ),
        {
            "client": (50, 50),
            "route": (320, 50),
            "authorize": (590, 50),
            "queue": (860, 50),
            "worker": (860, 194),
            "compute": (590, 194),
            "commit": (320, 194),
            "result": (50, 194),
        },
    ),
    DiagramSpec(
        "agent-decision.svg",
        "Agent decision pipeline",
        "本人用observationから検証済みactionまたは決定的fallbackを得る流れ。",
        (
            DiagramNode("view", "Player GameView", "private"),
            DiagramNode("request", "DecisionRequest", "value"),
            DiagramNode("session", "AgentSession", "core"),
            DiagramNode("adapter", "Provider Adapter", "adapter"),
            DiagramNode("schema", "Schema Validation", "process"),
            DiagramNode("legal", "Legality Check", "process"),
            DiagramNode("action", "Domain Action", "value"),
            DiagramNode("fallback", "Deterministic Fallback", "fallback"),
        ),
        (
            DiagramEdge("view", "request", "Project"),
            DiagramEdge("request", "session", "Decide"),
            DiagramEdge("session", "adapter", "Model port"),
            DiagramEdge("adapter", "schema", "Structured output"),
            DiagramEdge("schema", "legal", "Valid"),
            DiagramEdge("legal", "action", "Legal"),
            DiagramEdge("schema", "fallback", "Invalid"),
            DiagramEdge("legal", "fallback", "Illegal"),
            DiagramEdge("fallback", "action"),
        ),
        {
            "view": (50, 50),
            "request": (320, 50),
            "session": (590, 50),
            "adapter": (860, 50),
            "schema": (860, 194),
            "legal": (590, 194),
            "action": (320, 194),
            "fallback": (590, 338),
        },
    ),
    DiagramSpec(
        "simulation-lifecycle.svg",
        "Simulation lifecycle",
        "SimulationSessionが一stepずつ判断、手動入力、phase進行、停止を選ぶ流れ。",
        (
            DiagramNode("session", "SimulationSession", "core"),
            DiagramNode("inspect", "Inspect Game", "process"),
            DiagramNode("agent", "Agent Action", "process"),
            DiagramNode("manual", "Manual Input", "process"),
            DiagramNode("advance", "Advance Phase", "process"),
            DiagramNode("record", "Record Step", "value"),
            DiagramNode("continue", "Continue", "state"),
            DiagramNode("stop", "Stop Reason", "terminal"),
        ),
        (
            DiagramEdge("session", "inspect"),
            DiagramEdge("inspect", "agent", "Agent turn"),
            DiagramEdge("inspect", "manual", "Manual turn"),
            DiagramEdge("inspect", "advance", "No action"),
            DiagramEdge("agent", "record"),
            DiagramEdge("manual", "record"),
            DiagramEdge("advance", "record"),
            DiagramEdge("record", "continue", "Runnable"),
            DiagramEdge("continue", "inspect", "Next step"),
            DiagramEdge("record", "stop", "Finished / Wait / Limit / Cancel"),
        ),
        {
            "session": (50, 122),
            "inspect": (320, 122),
            "agent": (590, 50),
            "manual": (590, 194),
            "advance": (590, 338),
            "record": (860, 194),
            "continue": (1130, 50),
            "stop": (1130, 338),
        },
    ),
    DiagramSpec(
        "experiment-pipeline.svg",
        "Experiment pipeline",
        "比較条件から決定的Trialを計画し、保存済み結果からReportを作る流れ。",
        (
            DiagramNode("spec", "ExperimentSpec", "value"),
            DiagramNode("plan", "Plan Trials", "process"),
            DiagramNode("session", "SimulationSession", "core"),
            DiagramNode("trial", "Trial Artifact", "artifact"),
            DiagramNode("evaluate", "Evaluator", "process"),
            DiagramNode("report", "ExperimentReport", "artifact"),
            DiagramNode("resume", "Resume Check", "process"),
        ),
        (
            DiagramEdge("spec", "plan", "Conditions / Seeds / Rotation"),
            DiagramEdge("plan", "resume", "Trial IDs"),
            DiagramEdge("resume", "session", "Missing only"),
            DiagramEdge("session", "trial", "Atomic publish"),
            DiagramEdge("trial", "evaluate", "Completed trials"),
            DiagramEdge("evaluate", "report", "Deterministic metrics"),
            DiagramEdge("trial", "resume", "Existing checksum"),
        ),
        {
            "spec": (50, 50),
            "plan": (320, 50),
            "resume": (590, 50),
            "session": (860, 50),
            "trial": (860, 194),
            "evaluate": (590, 194),
            "report": (320, 194),
        },
    ),
    DiagramSpec(
        "information-boundaries.svg",
        "Information boundaries",
        "完全状態から公開情報、本人用observation、管理者revealを分離する流れ。",
        (
            DiagramNode("state", "Private Game State", "private"),
            DiagramNode("public_projection", "Public Projection", "process"),
            DiagramNode("observation", "Player Projection", "process"),
            DiagramNode("reveal", "Admin Reveal", "process"),
            DiagramNode("public", "Public State / Timeline", "public"),
            DiagramNode("player", "Player Observation", "private"),
            DiagramNode("admin", "Authorized Full View", "restricted"),
        ),
        (
            DiagramEdge("state", "public_projection", "Allowlist"),
            DiagramEdge("state", "observation", "Actor + Player"),
            DiagramEdge("state", "reveal", "Admin policy"),
            DiagramEdge("public_projection", "public"),
            DiagramEdge("observation", "player"),
            DiagramEdge("reveal", "admin"),
        ),
        {
            "state": (50, 194),
            "public_projection": (320, 50),
            "observation": (320, 194),
            "reveal": (320, 338),
            "public": (590, 50),
            "player": (590, 194),
            "admin": (590, 338),
        },
    ),
    DiagramSpec(
        "configuration-flow.svg",
        "Configuration flow",
        "既定値、環境変数、明示注入値を検証済みsettingsへ統合する流れ。",
        (
            DiagramNode("defaults", "Packaged Defaults", "source"),
            DiagramNode("environment", "Environment", "source"),
            DiagramNode("explicit", "Explicit Inputs", "source"),
            DiagramNode("sections", "Settings Sections", "process"),
            DiagramNode("validate", "Cross Validation", "process"),
            DiagramNode("settings", "AppSettings", "value"),
            DiagramNode("roots", "Composition Roots", "process"),
        ),
        (
            DiagramEdge("defaults", "sections"),
            DiagramEdge("environment", "sections", "Override"),
            DiagramEdge("explicit", "sections", "Override"),
            DiagramEdge("sections", "validate"),
            DiagramEdge("validate", "settings"),
            DiagramEdge("settings", "roots", "Inject values"),
        ),
        {
            "defaults": (50, 50),
            "environment": (50, 194),
            "explicit": (50, 338),
            "sections": (320, 194),
            "validate": (590, 194),
            "settings": (860, 194),
            "roots": (1130, 194),
        },
    ),
    DiagramSpec(
        "quality-pipeline.svg",
        "Quality pipeline",
        "変更影響からgateを選び、証拠と判定を保存する流れ。",
        (
            DiagramNode("change", "Revision + Change", "source"),
            DiagramNode("impact", "Impact Selection", "process"),
            DiagramNode("static", "Format / Lint / Type", "process"),
            DiagramNode("tests", "Tests / Contracts", "process"),
            DiagramNode("services", "Local Services / Browser", "process"),
            DiagramNode("evidence", "Evidence Manifest", "artifact"),
            DiagramNode("result", "Quality Result", "terminal"),
        ),
        (
            DiagramEdge("change", "impact"),
            DiagramEdge("impact", "static"),
            DiagramEdge("impact", "tests"),
            DiagramEdge("impact", "services"),
            DiagramEdge("static", "evidence"),
            DiagramEdge("tests", "evidence"),
            DiagramEdge("services", "evidence"),
            DiagramEdge("evidence", "result", "passed / failed / blocked / error"),
        ),
        {
            "change": (50, 194),
            "impact": (320, 194),
            "static": (590, 50),
            "tests": (590, 194),
            "services": (590, 338),
            "evidence": (860, 194),
            "result": (1130, 194),
        },
    ),
)

DIAGRAM_FILENAMES = (
    *(diagram.filename for diagram in STATIC_DIAGRAMS),
    "layer-dependencies.svg",
)


def write_diagrams(
    output_root: Path,
    layer_ids: frozenset[str],
    raw_layer_edges: object,
) -> None:
    """静的な設計図と実import依存図を決定的に生成する。"""
    for diagram in STATIC_DIAGRAMS:
        _write_svg(
            output_root / diagram.filename,
            diagram.title,
            diagram.description,
            diagram.nodes,
            diagram.edges,
            positions=diagram.positions,
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
        "実ソースコードのimportから得たPython layer間の依存。",
        layer_nodes,
        layer_edges,
        positions=_circular_positions(layer_nodes),
    )


def _write_svg(
    path: Path,
    title: str,
    description: str,
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
        f'<desc id="desc">{escape(description)}</desc>',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="7" '
        'refX="9" refY="3.5" orient="auto">'
        '<polygon points="0 0, 10 3.5, 0 7" fill="#52606d"/>'
        "</marker></defs>",
    ]
    for edge in edges:
        if edge.source not in positions or edge.target not in positions:
            raise ValueError(
                f"Diagram edge references an unknown node: {edge.source} -> {edge.target}"
            )
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
        "actor": "#e3f9e5",
        "adapter": "#f5e1f7",
        "aggregate": "#d9eafd",
        "application": "#e6f6ff",
        "artifact": "#f0f4f8",
        "definition": "#fff3c4",
        "core": "#d9eafd",
        "external": "#f5e1f7",
        "fallback": "#ffe3e3",
        "interface": "#e3f9e5",
        "layer": "#e6f6ff",
        "policy": "#fff3c4",
        "private": "#ffe3e3",
        "process": "#e6f6ff",
        "public": "#e3f9e5",
        "restricted": "#fff3c4",
        "source": "#f0f4f8",
        "state": "#d9eafd",
        "system": "#d9eafd",
        "terminal": "#fff3c4",
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


__all__ = ["DIAGRAM_FILENAMES", "write_diagrams"]
