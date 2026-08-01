"""正規setupとgame snapshotからAgent本人用contextを構築する."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from werewolf_agent.adapters.llm.models import AgentAbilityContext, AgentGameContext
from werewolf_agent.agents import AgentAbility, AgentIdentity, AgentWorld
from werewolf_agent.domain import GameState, GameView
from werewolf_agent.simulation import AgentMetadata


@dataclass(frozen=True)
class SetupAgentMetadataProvider:
    """正規setupと現在snapshotから本人用metadataを都度構築する."""

    setup: Mapping[str, object]
    snapshot: Callable[[], GameState]
    setup_checksum: str
    mechanics_checksum: str
    scenario_name: str = ""
    scenario_premise: str = ""

    def resolve(self, observation: GameView) -> AgentMetadata:
        """View所有者だけの役職・能力情報と公開世界設定を返す."""
        contexts = build_agent_game_contexts(
            self.setup,
            self.snapshot(),
            setup_checksum=self.setup_checksum,
            mechanics_checksum=self.mechanics_checksum,
            scenario_name=self.scenario_name,
            scenario_premise=self.scenario_premise,
        )
        return agent_metadata_from_game_context(contexts.get(observation.me.id))


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
    rule_sections = {
        key: mechanics.get(key) for key in ("discussion", "voting", "night", "lifecycle")
    }
    if (
        not isinstance(roles, Mapping)
        or not isinstance(abilities, Mapping)
        or any(not isinstance(value, Mapping) for value in rule_sections.values())
    ):
        return {}
    typed_sections = {key: _mapping(value) for key, value in rule_sections.items()}
    rules = {
        str(key): value for section in typed_sections.values() for key, value in section.items()
    }
    role_names = _mapping(theme.get("role_names"))
    role_objectives = _mapping(theme.get("role_objectives"))
    faction_names = _mapping(theme.get("faction_names"))
    ability_names = _mapping(theme.get("ability_names"))
    relevant_keys = {
        "kind",
        "message_max_chars",
        "cycles_per_day",
        "allow_self_vote",
        "allow_revision",
        "allow_action_revision",
        "tie_resolution",
        "reason_max_chars",
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


def agent_metadata_from_game_context(context: AgentGameContext | None) -> AgentMetadata:
    """既存adapter contextを標準Agent metadataへ変換する."""
    if context is None:
        return AgentMetadata()
    return AgentMetadata(
        identity=AgentIdentity(
            role_id=context.role_id,
            role_name=context.role_name,
            identity_faction_id=context.identity_faction,
            identity_faction_name=context.identity_faction_name,
            victory_team_id=context.victory_team,
            victory_team_name=context.victory_team_name,
            objective=context.objective,
            abilities=tuple(
                AgentAbility(
                    ability_id=ability.id,
                    name=ability.name,
                    kind=ability.kind,
                    remaining_uses=ability.remaining_uses,
                )
                for ability in context.abilities
            ),
        ),
        world=AgentWorld(
            theme_id=context.theme_id,
            theme_name=context.theme_name,
            premise=context.premise,
            setup_checksum=context.setup_checksum,
            mechanics_checksum=context.mechanics_checksum,
            relevant_rules=context.relevant_rules,
            action_names=context.action_names,
            phase_names=context.phase_names,
        ),
    )


__all__ = [
    "SetupAgentMetadataProvider",
    "agent_metadata_from_game_context",
    "build_agent_game_contexts",
]
