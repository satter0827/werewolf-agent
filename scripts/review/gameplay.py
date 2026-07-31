"""設定済みdomainをseed固定で完走し、公開情報だけのreview証拠を作る。"""

from __future__ import annotations

import random
from typing import Any

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.application.domain_codec import domain_to_data
from werewolf_agent.application.rules import rule_definition_from_values
from werewolf_agent.domain import Game, GameSetup, build_game_rules
from werewolf_agent.domain.state import (
    Action,
    ActionType,
    AvailableAction,
    EventVisibility,
    Player,
)
from werewolf_agent.setup import generate_players

MAX_PHASES = 64


def generate_gameplay_evidence(*, seed: int = 7) -> dict[str, Any]:
    """現在の設定resourceから再現可能な一局と公開timelineを返す。"""
    catalog = build_setup_catalog()
    setup = catalog.require_document(catalog.recommended_template_id)
    player_count = sum(setup.mechanics.role_counts.values())
    role_counts = dict(setup.mechanics.role_counts)
    rule_definition = rule_definition_from_values(
        player_count=player_count,
        role_counts=role_counts,
        rules=setup.mechanics.rules.model_dump(mode="json"),
        roles={
            role_id: role.model_dump(mode="json") for role_id, role in setup.mechanics.roles.items()
        },
        abilities={
            ability_id: ability.model_dump(mode="json")
            for ability_id, ability in setup.mechanics.abilities.items()
        },
    )
    rng = random.Random(seed)
    game = Game.create(
        GameSetup(
            players=tuple(
                Player(id=item.player_id, name=item.profile.name)
                for item in generate_players(
                    setup.player_generation, player_count=player_count, seed=seed
                )
            )
        ),
        rules=build_game_rules(rule_definition),
        random=rng,
    )
    operations: list[dict[str, object]] = []
    public_timeline = [
        domain_to_data(event)
        for event in game.creation_events
        if event.visibility is EventVisibility.PUBLIC
    ]
    for phase_index in range(MAX_PHASES):
        snapshot = game.snapshot()
        if snapshot.is_finished:
            break
        player_ids = list(snapshot.players)
        rng.shuffle(player_ids)
        for player_id in player_ids:
            observation = game.view_for(player_id)
            while observation.available_actions:
                action_type = rng.choice(observation.available_actions)
                action = _choose_action(rng, game, player_id, action_type, seed)
                events = game.submit(action)
                operations.append(
                    {
                        "phase_index": phase_index,
                        "day": snapshot.day,
                        "phase": snapshot.phase.value,
                        "actor_id": player_id,
                        "action": action_type.key,
                        "private_target_omitted": action.target_id is not None,
                    }
                )
                public_timeline.extend(
                    domain_to_data(event)
                    for event in events
                    if event.visibility is EventVisibility.PUBLIC
                )
                observation = game.view_for(player_id)
        public_timeline.extend(
            domain_to_data(event)
            for event in game.advance(rng)
            if event.visibility is EventVisibility.PUBLIC
        )
    snapshot = game.snapshot()
    if not snapshot.is_finished:
        raise RuntimeError(f"seed={seed}のゲームが{MAX_PHASES} phase以内に終了しませんでした。")
    return {
        "settings": {
            "seed": seed,
            "player_count": player_count,
            "role_counts": role_counts,
            "phase_order": [phase.value for phase in snapshot.config.phase_order],
            "external_llm": False,
        },
        "operations": operations,
        "public_timeline": public_timeline,
        "outcome": {
            "day": snapshot.day,
            "winner": snapshot.winner_id,
            "reason": snapshot.win_result.reason if snapshot.win_result else None,
        },
    }


def gameplay_summary(evidence: dict[str, Any]) -> str:
    """数値合否を付けず、証拠の読み方だけを短く示す。"""
    settings = evidence["settings"]
    outcome = evidence["outcome"]
    return "\n".join(
        [
            "# Gameplay review",
            "",
            f"- seed: `{settings['seed']}`",
            f"- player count: `{settings['player_count']}`",
            f"- winner: `{outcome['winner']}`",
            f"- finished day: `{outcome['day']}`",
            f"- operations: `{len(evidence['operations'])}`",
            f"- public timeline events: `{len(evidence['public_timeline'])}`",
            "",
            "面白さ、会話品質、進行の自然さは`gameplay.json`を読んで判断します。",
            "対象が解決するまで非公開の選択先は保存しません。",
            "",
        ]
    )


def _choose_action(
    rng: random.Random,
    game: Game,
    player_id: str,
    action_type: AvailableAction,
    seed: int,
) -> Action:
    if action_type.type is ActionType.SPEECH:
        return Action.speech(player_id, f"seed-{seed}の公開発言")
    if action_type.type is ActionType.PASS:
        return Action.pass_(player_id)
    targets = game.view_for(player_id).legal_targets[action_type.key]
    target_id = rng.choice(targets)
    if action_type.type is ActionType.VOTE:
        return Action.vote(player_id, target_id)
    if action_type.ability_id is not None:
        return Action.use_ability(player_id, action_type.ability_id, target_id)
    raise ValueError(f"unsupported available action: {action_type.key}")


__all__ = ["gameplay_summary", "generate_gameplay_evidence"]
