"""Coreと外部Rule Packへ同じ決定性・rollback・visibility契約を適用する."""

from __future__ import annotations

import random
from dataclasses import replace

import pytest

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.domain import (
    RULE_PACK_CONTRACT_VERSION,
    Action,
    ActionType,
    CompiledRuleSet,
    CoreRulePack,
    Game,
    GameEvent,
    GameSetup,
    GameState,
    GameView,
    Phase,
    Player,
    RulePackManifest,
    RulePackProvider,
    RulePolicyRegistry,
    RuleSetDefinition,
    RuleViolation,
)
from werewolf_agent.setup import generate_players, namespace_seed, rule_definition_from_values

_SEED = 73
_MAX_STEPS = 100


class _ExternalMirrorPack:
    """Coreの意味論を外部provider identityで提供するcontract fixture."""

    @property
    def manifest(self) -> RulePackManifest:
        return RulePackManifest(
            provider_id="external-mirror",
            contract_version=RULE_PACK_CONTRACT_VERSION,
            implementation_version="1.0.0",
            fingerprint="3" * 64,
        )

    def compile(self, definition: RuleSetDefinition) -> CompiledRuleSet:
        return replace(CoreRulePack().compile(definition), manifest=self.manifest)


def _inputs() -> tuple[RuleSetDefinition, GameSetup]:
    document = build_setup_catalog().require_document("standard_6")
    mechanics = document.mechanics
    player_count = sum(mechanics.role_counts.values())
    definition = rule_definition_from_values(
        player_count=player_count,
        role_counts=mechanics.role_counts,
        rules=mechanics.rules.to_mapping(),
        roles={key: value.to_mapping() for key, value in mechanics.roles.items()},
        abilities={key: value.to_mapping() for key, value in mechanics.abilities.items()},
    )
    generated = generate_players(document.player_generation, player_count=player_count, seed=_SEED)
    setup = GameSetup(tuple(Player(item.player_id, item.profile.name) for item in generated))
    return definition, setup


def _trace(
    provider: RulePackProvider,
) -> tuple[tuple[GameState, tuple[GameEvent, ...], tuple[GameView, ...]], ...]:
    definition, setup = _inputs()
    rules = RulePolicyRegistry((provider,)).compile(provider.manifest.provider_id, definition)
    game = Game.create(
        setup,
        rules=rules,
        random=random.Random(namespace_seed(_SEED, "role_assignment")),
    )
    phase_random = random.Random(namespace_seed(_SEED, "rule-pack-contract"))
    trace = [_trace_item(game, game.creation_events)]

    for _ in range(_MAX_STEPS):
        if game.snapshot().phase is Phase.FINISHED:
            break
        action = _first_legal_action(game)
        events = (
            tuple(game.submit(action)) if action is not None else tuple(game.advance(phase_random))
        )
        restored = Game.restore(game.snapshot(), rules=rules)
        assert _views(restored) == _views(game)
        trace.append(_trace_item(game, events))
    else:
        pytest.fail("Rule Pack contract scenario did not terminate")

    assert game.snapshot().phase is Phase.FINISHED
    return tuple(trace)


def _first_legal_action(game: Game) -> Action | None:
    for player_id in game.snapshot().players:
        view = game.view_for(player_id)
        if not view.available_actions:
            continue
        available = view.available_actions[0]
        targets = view.legal_targets.get(available.key, ())
        return Action(
            type=available.type,
            player_id=player_id,
            ability_id=available.ability_id,
            target_id=targets[0] if targets else None,
            message="契約を確認します。" if available.type is ActionType.SPEECH else None,
        )
    return None


def _views(game: Game) -> tuple[GameView, ...]:
    views = tuple(game.view_for(player_id) for player_id in game.snapshot().players)
    for view in views:
        for player in view.players:
            if player.id != view.me.id and player.id not in view.known_roles:
                assert player.role is None
    return views


def _trace_item(
    game: Game,
    events: tuple[GameEvent, ...],
) -> tuple[GameState, tuple[GameEvent, ...], tuple[GameView, ...]]:
    return game.snapshot(), events, _views(game)


@pytest.mark.parametrize(
    "provider",
    (CoreRulePack(), _ExternalMirrorPack()),
    ids=("core", "external"),
)
def test_rule_pack_contract_is_deterministic_secret_safe_and_atomic(
    provider: RulePackProvider,
) -> None:
    """同じ入力とseedの完全traceを再生成し、不正actionではstateを維持する."""
    first = _trace(provider)
    second = _trace(provider)

    assert first == second
    definition, setup = _inputs()
    rules = RulePolicyRegistry((provider,)).compile(provider.manifest.provider_id, definition)
    game = Game.create(setup, rules=rules, random=random.Random(7))
    before = game.snapshot()
    with pytest.raises(RuleViolation):
        game.submit(Action.pass_("unknown-player"))
    assert game.snapshot() == before
