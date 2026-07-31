"""Application復元時のRule Pack provenance契約を検証する."""

from __future__ import annotations

import random
from dataclasses import replace
from types import SimpleNamespace
from typing import cast

import pytest

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.application.domain_codec import domain_to_data
from werewolf_agent.application.errors import ConfigError
from werewolf_agent.application.handlers.common import _restore_game
from werewolf_agent.application.models import (
    ApplicationContext,
    GameApplicationConfig,
    StoredGame,
)
from werewolf_agent.application.ports import GameRepository
from werewolf_agent.domain import (
    RULE_PACK_CONTRACT_VERSION,
    CompiledRuleSet,
    CoreRulePack,
    Game,
    GameSetup,
    Player,
    RulePackManifest,
    RulePolicyRegistry,
    RuleSetDefinition,
)
from werewolf_agent.setup import rule_definition_from_values


class _ExternalProvider:
    @property
    def manifest(self) -> RulePackManifest:
        return RulePackManifest(
            provider_id="external",
            contract_version=RULE_PACK_CONTRACT_VERSION,
            implementation_version="1.0.0",
            fingerprint="1" * 64,
        )

    def compile(self, definition: RuleSetDefinition) -> CompiledRuleSet:
        return replace(CoreRulePack().compile(definition), manifest=self.manifest)


def _definition() -> RuleSetDefinition:
    mechanics = build_setup_catalog().require_document("standard_6").mechanics
    return rule_definition_from_values(
        player_count=sum(mechanics.role_counts.values()),
        role_counts=mechanics.role_counts,
        rules=mechanics.rules.to_mapping(),
        roles={role_id: role.to_mapping() for role_id, role in mechanics.roles.items()},
        abilities={
            ability_id: ability.to_mapping() for ability_id, ability in mechanics.abilities.items()
        },
    )


def _context(registry: RulePolicyRegistry) -> ApplicationContext:
    return ApplicationContext(
        repository=cast(GameRepository, object()),
        config=GameApplicationConfig(
            min_players=1,
            max_players=20,
            game_list_default_limit=20,
            game_list_max_limit=100,
            timeline_default_limit=50,
            timeline_max_limit=200,
        ),
        rule_packs=registry,
    )


def _stored_game(manifest: RulePackManifest) -> StoredGame:
    provider = _ExternalProvider()
    game = Game.create(
        GameSetup(tuple(Player(f"p{index}", f"Player {index}") for index in range(1, 7))),
        rules=provider.compile(_definition()),
        random=random.Random(7),
    )
    state = game.snapshot()
    return cast(
        StoredGame,
        SimpleNamespace(
            private_state=domain_to_data(state),
            pending_actions=domain_to_data(state.pending_actions),
            config={"rule_pack_manifest": manifest.to_mapping()},
        ),
    )


def test_restore_requires_the_exact_registered_rule_pack_manifest() -> None:
    """同じprovider IDでも実装fingerprintが異なる復元を拒否する."""
    provider = _ExternalProvider()
    run = _stored_game(provider.manifest)

    restored = _restore_game(run, _context(RulePolicyRegistry((provider,))))

    assert restored.rule_pack_manifest == provider.manifest
    changed = replace(provider.manifest, fingerprint="2" * 64)
    with pytest.raises(ConfigError, match="再構築できません"):
        _restore_game(_stored_game(changed), _context(RulePolicyRegistry((provider,))))


def test_restore_does_not_fall_back_to_core_for_an_unknown_provider() -> None:
    """保存済み外部providerが未登録でもCoreへ暗黙fallbackしない."""
    provider = _ExternalProvider()

    with pytest.raises(ConfigError, match="再構築できません"):
        _restore_game(
            _stored_game(provider.manifest),
            _context(RulePolicyRegistry((CoreRulePack(),))),
        )
