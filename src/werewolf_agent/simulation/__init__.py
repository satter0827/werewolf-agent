"""headlessな単一ゲーム実行の公開contractを提供する."""

from werewolf_agent.simulation.contracts import (
    SIMULATION_CONTRACT_VERSION,
    AgentMetadata,
    AgentMetadataProvider,
    DecisionExecutor,
    DecisionTraceSink,
    NullDecisionTraceSink,
    PlayerController,
    SimulationLimits,
    SimulationResult,
    SimulationSpec,
    SimulationStep,
    SimulationStepKind,
    SimulationStopReason,
)
from werewolf_agent.simulation.session import (
    CancellationToken,
    SimulationRunner,
    SimulationSession,
    SynchronousDecisionExecutor,
)

__all__ = [
    "SIMULATION_CONTRACT_VERSION",
    "AgentMetadata",
    "AgentMetadataProvider",
    "CancellationToken",
    "DecisionExecutor",
    "DecisionTraceSink",
    "NullDecisionTraceSink",
    "PlayerController",
    "SimulationLimits",
    "SimulationResult",
    "SimulationRunner",
    "SimulationSession",
    "SimulationSpec",
    "SimulationStep",
    "SimulationStepKind",
    "SimulationStopReason",
    "SynchronousDecisionExecutor",
]
