"""application composition向けRule Pack registry契約とfactory."""

from typing import Protocol

from werewolf_agent.domain import (
    CompiledRuleSet,
    CoreRulePack,
    RulePackManifest,
    RulePolicyRegistry,
    RuleSetDefinition,
)


class RulePackRegistry(Protocol):
    """applicationが利用する明示登録済みRule Pack registry契約."""

    def compile(
        self,
        provider_id: str,
        definition: RuleSetDefinition,
        *,
        expected_manifest: RulePackManifest | None = None,
    ) -> CompiledRuleSet:
        """登録済みproviderから検証済みrulesetを構築する."""
        ...


def create_core_rule_policy_registry() -> RulePackRegistry:
    """組み込みproviderだけを明示登録したregistryを返す."""
    return RulePolicyRegistry((CoreRulePack(),))


__all__ = ["RulePackRegistry", "create_core_rule_policy_registry"]
