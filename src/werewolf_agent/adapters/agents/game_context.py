"""正規setupとgame snapshotからAgent本人用contextを構築する."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werewolf_agent.adapters.llm.models import AgentAbilityContext, AgentGameContext


def build_agent_game_contexts(
    setup: Mapping[str, object],
    snapshot: Any,
    *,
    setup_checksum: str,
    mechanics_checksum: str,
    scenario_name: str = "",
    scenario_premise: str = "",
) -> dict[str, AgentGameContext]:
    """他プレイヤーの役職や未解決行動を含めず本人用contextを構築する."""
    mechanics = setup.get("mechanics")
    theme = setup.get("theme")
    if not isinstance(mechanics, Mapping) or not isinstance(theme, Mapping):
        return {}
    roles = mechanics.get("roles")
    abilities = mechanics.get("abilities")
    rules = mechanics.get("rules")
    if (
        not isinstance(roles, Mapping)
        or not isinstance(abilities, Mapping)
        or not isinstance(rules, Mapping)
    ):
        return {}
    role_names = _mapping(theme.get("role_names"))
    role_objectives = _mapping(theme.get("role_objectives"))
    faction_names = _mapping(theme.get("faction_names"))
    ability_names = _mapping(theme.get("ability_names"))
    relevant_keys = {
        "day_speech_limit_per_player",
        "allow_self_vote",
        "allow_vote_revision",
        "allow_night_action_revision",
        "vote_tie_resolution",
        "starting_phase",
        "reveal_role_on_death",
        "require_all_actions_before_advance",
    }
    contexts: dict[str, AgentGameContext] = {}
    for player in snapshot.players.values():
        if player.role is None:
            continue
        role = roles.get(player.role)
        if not isinstance(role, Mapping):
            continue
        ability_contexts: list[AgentAbilityContext] = []
        for ability_id_value in role.get("abilities") or []:
            ability_id = str(ability_id_value)
            ability = abilities.get(ability_id)
            if not isinstance(ability, Mapping):
                continue
            max_uses = ability.get("max_uses")
            used = snapshot.ability_uses.get(player.id, {}).get(ability_id, 0)
            if max_uses == "unlimited":
                remaining = None
            elif isinstance(max_uses, int) and not isinstance(max_uses, bool):
                remaining = max(0, max_uses - used)
            else:
                raise ValueError("ability max_uses must be an integer or unlimited")
            ability_contexts.append(
                AgentAbilityContext(
                    id=ability_id,
                    name=str(ability_names.get(ability_id) or ability.get("label") or ability_id),
                    kind=str(ability.get("kind") or ""),
                    remaining_uses=remaining,
                )
            )
        identity_faction = str(role.get("identity_faction") or "")
        victory_team = str(role.get("victory_team") or "")
        contexts[player.id] = AgentGameContext(
            theme_id=str(theme.get("id") or ""),
            theme_name=scenario_name.strip() or str(theme.get("name") or ""),
            premise=scenario_premise.strip() or str(theme.get("premise") or ""),
            role_id=player.role,
            role_name=str(role_names.get(player.role) or role.get("label") or player.role),
            identity_faction=identity_faction,
            identity_faction_name=str(faction_names.get(identity_faction) or identity_faction),
            victory_team=victory_team,
            victory_team_name=str(faction_names.get(victory_team) or victory_team),
            objective=str(role_objectives.get(player.role) or role.get("objective") or ""),
            abilities=tuple(ability_contexts),
            relevant_rules={key: rules[key] for key in sorted(relevant_keys) if key in rules},
            action_names={
                str(key): str(value) for key, value in _mapping(theme.get("action_names")).items()
            },
            phase_names={
                str(key): str(value) for key, value in _mapping(theme.get("phase_names")).items()
            },
            setup_checksum=setup_checksum,
            mechanics_checksum=mechanics_checksum,
        )
    return contexts


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


__all__ = ["build_agent_game_contexts"]
