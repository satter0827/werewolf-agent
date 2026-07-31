"""外部Rule Packへ適用できる標準ライブラリ契約テストを提供する."""

from __future__ import annotations

import random

from werewolf_agent.domain.definitions import RuleSetDefinition
from werewolf_agent.domain.errors import RuleViolation
from werewolf_agent.domain.game import Game
from werewolf_agent.domain.rule_packs import RulePackProvider, RulePolicyRegistry
from werewolf_agent.domain.state import (
    Action,
    ActionType,
    GameEvent,
    GameSetup,
    GameState,
    GameView,
    Phase,
)


def assert_rule_pack_contract(
    provider: RulePackProvider,
    *,
    definition: RuleSetDefinition,
    setup: GameSetup,
    seed: int = 73,
    max_steps: int = 100,
) -> None:
    """決定性、復元、秘匿性、atomicity、停止性の共通契約を検証する."""
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")
    first = _trace(provider, definition, setup, seed, max_steps)
    second = _trace(provider, definition, setup, seed, max_steps)
    _require(
        first == second,
        "same definition, setup, and seed must reproduce the complete trace",
    )

    rules = RulePolicyRegistry((provider,)).compile(provider.manifest.provider_id, definition)
    game = Game.create(setup, rules=rules, random=random.Random(seed))
    before = game.snapshot()
    try:
        game.submit(Action.pass_("unknown-player"))
    except RuleViolation:
        pass
    else:
        raise AssertionError("an invalid action must raise RuleViolation")
    _require(game.snapshot() == before, "an invalid action must not mutate game state")


def _trace(
    provider: RulePackProvider,
    definition: RuleSetDefinition,
    setup: GameSetup,
    seed: int,
    max_steps: int,
) -> tuple[tuple[GameState, tuple[GameEvent, ...], tuple[GameView, ...]], ...]:
    rules = RulePolicyRegistry((provider,)).compile(provider.manifest.provider_id, definition)
    game = Game.create(setup, rules=rules, random=random.Random(seed))
    phase_random = random.Random(seed + 1)
    trace = [_trace_item(game, game.creation_events)]
    for _ in range(max_steps):
        if game.snapshot().phase is Phase.FINISHED:
            break
        action = _first_legal_action(game)
        events = (
            tuple(game.submit(action)) if action is not None else tuple(game.advance(phase_random))
        )
        restored = Game.restore(game.snapshot(), rules=rules)
        _require(_views(restored) == _views(game), "restored views must match live views")
        trace.append(_trace_item(game, events))
    else:
        raise AssertionError("Rule Pack contract scenario did not terminate")
    _require(game.snapshot().phase is Phase.FINISHED, "scenario must finish")
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
                _require(player.role is None, "a player view must not expose an unknown role")
    return views


def _trace_item(
    game: Game,
    events: tuple[GameEvent, ...],
) -> tuple[GameState, tuple[GameEvent, ...], tuple[GameView, ...]]:
    return game.snapshot(), events, _views(game)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


__all__ = ["assert_rule_pack_contract"]
