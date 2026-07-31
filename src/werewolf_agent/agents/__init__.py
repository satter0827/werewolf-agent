"""外部注入可能な標準ライブラリAgent SDKを公開する."""

from werewolf_agent.agents.builtins import (
    FaultAgentFactory,
    HeuristicAgentFactory,
    RandomLegalAgentFactory,
    ScriptedAgentFactory,
)
from werewolf_agent.agents.conformance import assert_agent_factory_contract
from werewolf_agent.agents.contracts import (
    AGENT_CONTRACT_VERSION,
    AgentAbility,
    AgentContext,
    AgentDecisionError,
    AgentFactory,
    AgentIdentity,
    AgentObservation,
    AgentSession,
    AgentSpec,
    AgentWorld,
    DecisionOption,
    DecisionRequest,
    DecisionResponse,
    DecisionTrace,
    ObservedPlayer,
    PublicTimelineEvent,
)

__all__ = [
    "AGENT_CONTRACT_VERSION",
    "AgentAbility",
    "AgentContext",
    "AgentDecisionError",
    "AgentFactory",
    "AgentIdentity",
    "AgentObservation",
    "AgentSession",
    "AgentSpec",
    "AgentWorld",
    "DecisionOption",
    "DecisionRequest",
    "DecisionResponse",
    "DecisionTrace",
    "FaultAgentFactory",
    "HeuristicAgentFactory",
    "ObservedPlayer",
    "PublicTimelineEvent",
    "RandomLegalAgentFactory",
    "ScriptedAgentFactory",
    "assert_agent_factory_contract",
]
