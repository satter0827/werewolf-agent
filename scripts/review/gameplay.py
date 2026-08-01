"""設定済みdomainをseed固定で完走し、公開情報だけのreview証拠を作る。"""

from __future__ import annotations

from typing import Any

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.agents import RandomLegalAgentFactory
from werewolf_agent.application.domain_codec import domain_to_data
from werewolf_agent.domain import EventVisibility, GameSetup, Player, build_game_rules
from werewolf_agent.setup import generate_players, rule_definition_from_values
from werewolf_agent.simulation import (
    PlayerController,
    SimulationLimits,
    SimulationRunner,
    SimulationSpec,
    SimulationStepKind,
    SimulationStopReason,
)

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
        rules=setup.mechanics.rules.to_mapping(),
        roles={role_id: role.to_mapping() for role_id, role in setup.mechanics.roles.items()},
        abilities={
            ability_id: ability.to_mapping()
            for ability_id, ability in setup.mechanics.abilities.items()
        },
    )
    players = tuple(
        Player(id=item.player_id, name=item.profile.name)
        for item in generate_players(
            setup.player_generation,
            player_count=player_count,
            seed=seed,
        )
    )
    spec = SimulationSpec(
        simulation_id=f"gameplay-review:{seed}",
        game_id=f"gameplay-review:{seed}",
        seed=seed,
        controllers={
            player.id: PlayerController(
                player.id,
                RandomLegalAgentFactory(speech=f"seed-{seed}の公開発言"),
            )
            for player in players
        },
        limits=SimulationLimits(max_actions=10_000, max_phases=MAX_PHASES),
    )
    session = SimulationRunner().create(
        GameSetup(players=players),
        rules=build_game_rules(rule_definition),
        spec=spec,
    )
    game = session.game
    operations: list[dict[str, object]] = []
    public_timeline = [
        domain_to_data(event)
        for event in game.creation_events
        if event.visibility is EventVisibility.PUBLIC
    ]
    phase_index = 0
    try:
        while True:
            step = session.step()
            public_timeline.extend(
                domain_to_data(event)
                for event in step.events
                if event.visibility is EventVisibility.PUBLIC
            )
            if step.kind is SimulationStepKind.AGENT_ACTION:
                public_actor = step.action_type == "speech"
                operations.append(
                    {
                        "phase_index": phase_index,
                        "day": step.day_before,
                        "phase": step.phase_before,
                        "actor_id": step.actor_id if public_actor else None,
                        "action": step.action_type,
                        "private_actor_omitted": not public_actor,
                        "private_target_omitted": step.action_type in {"vote", "use_ability"},
                    }
                )
            elif step.kind is SimulationStepKind.PHASE_ADVANCED:
                phase_index += 1
            if step.stop_reason is not None:
                break
    finally:
        session.close()
    snapshot = game.snapshot()
    if step.stop_reason is not SimulationStopReason.FINISHED:
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


__all__ = ["gameplay_summary", "generate_gameplay_evidence"]
