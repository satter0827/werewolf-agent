"""worker compositionの外部注入契約."""

from typing import cast

import pytest

from werewolf_agent.agents import AgentFactory, RandomLegalAgentFactory
from werewolf_agent.domain import RulePolicyRegistry
from werewolf_agent.worker.composition import (
    WorkerDependencies,
    create_core_worker_dependencies,
)


def test_core_worker_dependencies_register_only_the_core_rule_pack() -> None:
    """通常起動が暗黙探索なしで組み込みproviderだけを登録する."""
    dependencies = create_core_worker_dependencies()
    registry = cast(RulePolicyRegistry, dependencies.rule_packs)

    assert registry.provider_ids == ("core",)
    assert dependencies.agent_factories == {}


def test_worker_dependencies_copy_and_freeze_injected_agent_factories() -> None:
    """外部mappingの変更をprocess構成へ波及させない."""
    factory = RandomLegalAgentFactory()
    source: dict[str, AgentFactory] = {"p1": factory}
    dependencies = WorkerDependencies(
        rule_packs=create_core_worker_dependencies().rule_packs,
        agent_factories=source,
    )

    source.clear()

    assert dependencies.agent_factories == {"p1": factory}
    with pytest.raises(TypeError):
        cast(dict[str, AgentFactory], dependencies.agent_factories)["p2"] = factory
