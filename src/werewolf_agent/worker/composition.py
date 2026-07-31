"""workerへ明示注入するRule PackとAgent Factoryを定義する."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from werewolf_agent.agents import AgentFactory
from werewolf_agent.application import (
    RulePackRegistry,
    create_core_rule_policy_registry,
)


@dataclass(frozen=True)
class WorkerDependencies:
    """一つのworker processが使用する信頼済み拡張を保持する."""

    rule_packs: RulePackRegistry
    agent_factories: Mapping[str, AgentFactory]

    def __post_init__(self) -> None:
        """外部mappingの後続変更からprocess構成を隔離する."""
        object.__setattr__(self, "agent_factories", MappingProxyType(dict(self.agent_factories)))


def create_core_worker_dependencies() -> WorkerDependencies:
    """組み込みRule Packと既定Agent adapterを使うworker構成を返す."""
    return WorkerDependencies(
        rule_packs=create_core_rule_policy_registry(),
        agent_factories={},
    )


__all__ = ["WorkerDependencies", "create_core_worker_dependencies"]
