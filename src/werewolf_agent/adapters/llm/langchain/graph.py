"""LangChain-backed decision services for visible player observations."""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any

from langgraph.graph import END, START, StateGraph

from werewolf_agent.adapters.llm.langchain.constants import (
    DECISION_GRAPH_END,
    DECISION_GRAPH_NODE_BUILD_PROMPT_CONTEXT,
    DECISION_GRAPH_NODE_CHOOSE_REQUIRED_ACTION,
    DECISION_GRAPH_NODE_DETERMINISTIC_FALLBACK,
    DECISION_GRAPH_NODE_INVOKE_MODEL,
    DECISION_GRAPH_NODE_NORMALIZE_OBSERVATION,
    DECISION_GRAPH_NODE_RANK_TARGETS,
    DECISION_GRAPH_NODE_REPAIR_ONCE,
    DECISION_GRAPH_NODE_ROLE_HINT,
    DECISION_GRAPH_NODE_VALIDATE_ACTION,
    DECISION_GRAPH_START,
    ROUTE_FAILED,
    ROUTE_INVALID,
    ROUTE_VALID,
)
from werewolf_agent.adapters.llm.langchain.models import _DecisionGraphState
from werewolf_agent.adapters.llm.messages import (
    MESSAGE_OBSERVATION_BELONGS_TO_ANOTHER_PLAYER,
    MESSAGE_PLAYER_IS_DEAD,
    message_no_action_for_phase,
)
from werewolf_agent.agents.definitions import (
    AgentStrategyDefinition,
)
from werewolf_agent.agents.models import (
    AgentDecision,
    AgentObservation,
    AgentPlayerStatus,
)


def _compile_decision_graph(
    provider: Any,
    strategy: AgentStrategyDefinition,
) -> Any:
    graph = StateGraph(_DecisionGraphState)
    registry = _node_registry(provider)
    for node_id in strategy.nodes:
        graph.add_node(node_id, registry[node_id])
    routed_sources = {route.from_node for route in strategy.routes}
    for edge in strategy.edges:
        if edge.from_node in routed_sources:
            continue
        graph.add_edge(_graph_endpoint(edge.from_node), _graph_endpoint(edge.to_node))
    for route in strategy.routes:
        path_map: dict[Hashable, str] = {}
        if route.valid is not None:
            path_map[ROUTE_VALID] = _graph_endpoint(route.valid)
        if route.invalid is not None:
            path_map[ROUTE_INVALID] = _graph_endpoint(route.invalid)
        if route.failed is not None:
            path_map[ROUTE_FAILED] = _graph_endpoint(route.failed)
        graph.add_conditional_edges(route.from_node, _route_validation, path_map=path_map)
    return graph.compile()


def _node_registry(provider: Any) -> dict[str, Any]:
    return {
        DECISION_GRAPH_NODE_NORMALIZE_OBSERVATION: provider._node_normalize_observation,
        DECISION_GRAPH_NODE_CHOOSE_REQUIRED_ACTION: provider._node_choose_required_action,
        DECISION_GRAPH_NODE_ROLE_HINT: provider._node_role_hint,
        DECISION_GRAPH_NODE_RANK_TARGETS: provider._node_rank_targets,
        DECISION_GRAPH_NODE_BUILD_PROMPT_CONTEXT: provider._node_build_prompt_context,
        DECISION_GRAPH_NODE_INVOKE_MODEL: provider._node_invoke_model,
        DECISION_GRAPH_NODE_VALIDATE_ACTION: provider._node_validate_action,
        DECISION_GRAPH_NODE_REPAIR_ONCE: provider._node_repair_once,
        DECISION_GRAPH_NODE_DETERMINISTIC_FALLBACK: provider._node_deterministic_fallback,
    }


def _graph_endpoint(node_id: str) -> str:
    if node_id == DECISION_GRAPH_START:
        return START
    if node_id == DECISION_GRAPH_END:
        return END
    return node_id


def _route_validation(state: _DecisionGraphState) -> str:
    route = str(state.get("route") or ROUTE_FAILED)
    if route in {ROUTE_VALID, ROUTE_INVALID, ROUTE_FAILED}:
        return route
    return ROUTE_FAILED


def _preflight_decision(
    player_id: str,
    observation: AgentObservation,
) -> AgentDecision | None:
    if observation.me.id != player_id:
        return AgentDecision.pass_(
            player_id=player_id,
            reason=MESSAGE_OBSERVATION_BELONGS_TO_ANOTHER_PLAYER,
        )
    if observation.me.status is not AgentPlayerStatus.ALIVE:
        return AgentDecision.pass_(player_id=player_id, reason=MESSAGE_PLAYER_IS_DEAD)
    if not observation.available_actions:
        return AgentDecision.pass_(
            player_id=player_id,
            reason=message_no_action_for_phase(observation.phase.value),
        )
    return None
