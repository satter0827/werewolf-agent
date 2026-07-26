"""LangChain-backed decision services for visible player observations."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from werewolf_agent.adapters.llm.langchain.constants import (
    DECISION_GRAPH_NODE_BUILD_PROMPT_CONTEXT,
    DECISION_GRAPH_NODE_CHOOSE_REQUIRED_ACTION,
    DECISION_GRAPH_NODE_DETERMINISTIC_FALLBACK,
    DECISION_GRAPH_NODE_INVOKE_MODEL,
    DECISION_GRAPH_NODE_NORMALIZE_OBSERVATION,
    DECISION_GRAPH_NODE_RANK_TARGETS,
    DECISION_GRAPH_NODE_REPAIR_ONCE,
    DECISION_GRAPH_NODE_ROLE_HINT,
    DECISION_GRAPH_NODE_VALIDATE_ACTION,
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
from werewolf_agent.agents.models import (
    AgentDecision,
    AgentObservation,
    AgentPlayerStatus,
)


def _compile_decision_graph(provider: Any) -> Any:
    """Compile the single code-owned decision graph."""
    graph = StateGraph(_DecisionGraphState)
    for node_id, node in _node_registry(provider).items():
        graph.add_node(node_id, node)
    graph.add_edge(START, DECISION_GRAPH_NODE_NORMALIZE_OBSERVATION)
    graph.add_edge(
        DECISION_GRAPH_NODE_NORMALIZE_OBSERVATION,
        DECISION_GRAPH_NODE_CHOOSE_REQUIRED_ACTION,
    )
    graph.add_edge(DECISION_GRAPH_NODE_CHOOSE_REQUIRED_ACTION, DECISION_GRAPH_NODE_ROLE_HINT)
    graph.add_edge(DECISION_GRAPH_NODE_ROLE_HINT, DECISION_GRAPH_NODE_RANK_TARGETS)
    graph.add_edge(DECISION_GRAPH_NODE_RANK_TARGETS, DECISION_GRAPH_NODE_BUILD_PROMPT_CONTEXT)
    graph.add_edge(DECISION_GRAPH_NODE_BUILD_PROMPT_CONTEXT, DECISION_GRAPH_NODE_INVOKE_MODEL)
    graph.add_edge(DECISION_GRAPH_NODE_INVOKE_MODEL, DECISION_GRAPH_NODE_VALIDATE_ACTION)
    graph.add_conditional_edges(
        DECISION_GRAPH_NODE_VALIDATE_ACTION,
        _route_validation,
        path_map={
            ROUTE_VALID: END,
            ROUTE_INVALID: DECISION_GRAPH_NODE_REPAIR_ONCE,
            ROUTE_FAILED: DECISION_GRAPH_NODE_DETERMINISTIC_FALLBACK,
        },
    )
    graph.add_edge(DECISION_GRAPH_NODE_REPAIR_ONCE, DECISION_GRAPH_NODE_VALIDATE_ACTION)
    graph.add_edge(DECISION_GRAPH_NODE_DETERMINISTIC_FALLBACK, END)
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
