"""Configured ability recording and deterministic night resolution."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import replace
from itertools import groupby

from werewolf_agent.domain._messages import (
    MESSAGE_CANNOT_INSPECT_UNASSIGNED_ROLE,
    MESSAGE_EXPECTED_NIGHT_ACTION,
    MESSAGE_UNSUPPORTED_NIGHT_ACTION,
)
from werewolf_agent.domain.errors import GameError
from werewolf_agent.domain.rules.player_rules import (
    faction_for_role,
    mark_dead,
    player_by_id,
    require_alive,
    require_phase,
    resolve_death_reactions,
)
from werewolf_agent.domain.state import (
    AbilityDefinition,
    Action,
    ActionType,
    GameState,
    InspectionResult,
    NightResult,
    Phase,
)


def record_night_action(
    snapshot: GameState,
    pending_actions: Mapping[str, Action],
    action: Action,
) -> dict[str, Action]:
    """Validate and return pending ability actions with one action recorded."""
    require_phase(snapshot, Phase.NIGHT)
    _validate_night_action(snapshot, action)
    updated_actions = dict(pending_actions)
    updated_actions[action.player_id] = action
    return updated_actions


def resolve_night(
    snapshot: GameState,
    pending_actions: Mapping[str, Action],
    rng: random.Random,
) -> tuple[GameState, NightResult]:
    """Resolve configured active abilities by component kind."""
    require_phase(snapshot, Phase.NIGHT)
    ability_actions = [
        action for action in pending_actions.values() if action.type is ActionType.USE_ABILITY
    ]
    ordered = sorted(
        ability_actions,
        key=lambda action: (
            _ability_for_action(snapshot, action).resolution_priority,
            action.ability_id or "",
            action.player_id,
        ),
    )
    protected_player_ids: set[str] = set()
    killed_player_ids: set[str] = set()
    attacked_player_ids: list[str] = []
    inspection_results: list[InspectionResult] = []
    passive_uses: list[tuple[str, str]] = []
    for _, grouped_actions in groupby(
        ordered,
        key=lambda action: (
            _ability_for_action(snapshot, action).resolution_priority,
            action.ability_id,
        ),
    ):
        actions = list(grouped_actions)
        ability = _ability_for_action(snapshot, actions[0])
        if ability.kind == "protect":
            protected_player_ids.update(_target(action) for action in actions)
            continue
        if ability.kind == "attack":
            if ability.tie_resolution is None:
                raise ValueError("validated attack ability is missing tie_resolution")
            target_id = _resolve_group_target(
                actions,
                rng,
                tie_resolution=ability.tie_resolution,
            )
            if target_id is None:
                continue
            attacked_player_ids.append(target_id)
            if target_id in protected_player_ids:
                continue
            immunity_id = _eligible_passive(
                snapshot,
                target_id,
                "immunity",
                source_kind="attack",
            )
            if immunity_id is not None:
                passive_uses.append((target_id, immunity_id))
            else:
                killed_player_ids.add(target_id)
            continue
        if ability.kind == "eliminate":
            for action in actions:
                target_id = _target(action)
                if target_id in protected_player_ids:
                    continue
                immunity_id = _eligible_passive(
                    snapshot,
                    target_id,
                    "immunity",
                    source_kind="eliminate",
                )
                if immunity_id is not None:
                    passive_uses.append((target_id, immunity_id))
                else:
                    killed_player_ids.add(target_id)
            continue
        if ability.kind == "inspect":
            for action in actions:
                inspection = _inspect(snapshot, action)
                inspection_results.append(inspection)
                vulnerability_id = _eligible_passive(
                    snapshot,
                    inspection.target_id,
                    "vulnerability",
                    source_kind="inspect",
                )
                if vulnerability_id is not None:
                    passive_uses.append((inspection.target_id, vulnerability_id))
                    immunity_id = _eligible_passive(
                        snapshot,
                        inspection.target_id,
                        "immunity",
                        source_kind="inspect",
                    )
                    if immunity_id is not None:
                        passive_uses.append((inspection.target_id, immunity_id))
                    else:
                        killed_player_ids.add(inspection.target_id)

    updated_snapshot = snapshot
    for player_id in sorted(killed_player_ids):
        if updated_snapshot.players[player_id].is_alive:
            updated_snapshot = mark_dead(updated_snapshot, player_id, killed_night=snapshot.day)
    updated_snapshot, reaction_deaths = resolve_death_reactions(
        updated_snapshot,
        sorted(killed_player_ids),
        rng,
        during_night=True,
    )
    killed_player_ids.update(reaction_deaths)
    updated_snapshot = _consume_limited_abilities(
        updated_snapshot,
        ordered,
        passive_uses=passive_uses,
    )
    killed_ids = tuple(sorted(killed_player_ids))
    result = NightResult(
        day=snapshot.day,
        attacked_player_id=attacked_player_ids[0] if attacked_player_ids else None,
        protected_player_id=next(iter(sorted(protected_player_ids)), None),
        killed_player_id=killed_ids[0] if killed_ids else None,
        killed_player_ids=killed_ids,
        inspections=tuple(inspection_results),
        ability_targets={
            action.player_id: {action.ability_id: _target(action)}
            for action in ordered
            if action.ability_id is not None
        },
    )
    history = replace(updated_snapshot.history, nights=(*updated_snapshot.history.nights, result))
    return replace(updated_snapshot, history=history), result


def _validate_night_action(snapshot: GameState, action: Action) -> None:
    if action.type is ActionType.PASS:
        return
    if action.type is not ActionType.USE_ABILITY:
        raise GameError(MESSAGE_EXPECTED_NIGHT_ACTION)
    ability = _ability_for_action(snapshot, action)
    if ability.kind not in {"attack", "inspect", "protect", "eliminate"}:
        raise GameError(MESSAGE_UNSUPPORTED_NIGHT_ACTION)
    target_id = _target(action)
    require_alive(snapshot, target_id)


def _ability_for_action(snapshot: GameState, action: Action) -> AbilityDefinition:
    actor = require_alive(snapshot, action.player_id)
    if actor.role is None or action.ability_id is None:
        raise GameError(MESSAGE_UNSUPPORTED_NIGHT_ACTION)
    role = snapshot.config.roles.require_role(actor.role)
    if action.ability_id not in role.abilities:
        raise GameError(
            MESSAGE_UNSUPPORTED_NIGHT_ACTION,
            context={"player_id": action.player_id, "ability_id": action.ability_id},
        )
    return snapshot.config.abilities[action.ability_id]


def _target(action: Action) -> str:
    if action.type is not ActionType.USE_ABILITY or action.target_id is None:
        raise GameError(MESSAGE_EXPECTED_NIGHT_ACTION)
    return action.target_id


def _resolve_group_target(
    actions: list[Action],
    rng: random.Random,
    *,
    tie_resolution: str,
) -> str | None:
    if not actions:
        return None
    counts = Counter(_target(action) for action in actions)
    maximum = max(counts.values())
    tied = sorted(target_id for target_id, count in counts.items() if count == maximum)
    if len(tied) == 1:
        return tied[0]
    if tie_resolution == "no_action":
        return None
    return rng.choice(tied)


def _inspect(snapshot: GameState, action: Action) -> InspectionResult:
    actor = require_alive(snapshot, action.player_id)
    target = player_by_id(snapshot, _target(action))
    if target.role is None:
        raise GameError(
            MESSAGE_CANNOT_INSPECT_UNASSIGNED_ROLE,
            context={"target_id": target.id},
        )
    return InspectionResult(
        day=snapshot.day,
        player_id=actor.id,
        ability_id=action.ability_id or "",
        target_id=target.id,
        target_role=target.role,
        target_faction=faction_for_role(snapshot, target.role),
    )


def _eligible_passive(
    snapshot: GameState,
    player_id: str,
    kind: str,
    *,
    source_kind: str,
) -> str | None:
    role_id = snapshot.players[player_id].role
    if role_id is None:
        return None
    role = snapshot.config.roles.require_role(role_id)
    for ability_id in sorted(
        role.abilities,
        key=lambda item: (snapshot.config.abilities[item].resolution_priority, item),
    ):
        ability = snapshot.config.abilities[ability_id]
        used = snapshot.ability_uses.get(player_id, {}).get(ability_id, 0)
        if (
            ability.kind == kind
            and ability.phase is snapshot.phase
            and snapshot.day >= ability.start_day
            and (snapshot.day != 1 or ability.enabled_first_night)
            and (ability.max_uses is None or used < ability.max_uses)
            and (not ability.source_kinds or source_kind in ability.source_kinds)
        ):
            return ability_id
    return None


def _consume_limited_abilities(
    snapshot: GameState,
    actions: Iterable[Action],
    *,
    passive_uses: Iterable[tuple[str, str]] = (),
) -> GameState:
    uses = {player_id: dict(values) for player_id, values in snapshot.ability_uses.items()}
    for action in actions:
        if action.ability_id is None:
            continue
        ability = snapshot.config.abilities[action.ability_id]
        if ability.max_uses is None:
            continue
        player_uses = uses.setdefault(action.player_id, {})
        player_uses[action.ability_id] = player_uses.get(action.ability_id, 0) + 1
    for player_id, ability_id in passive_uses:
        ability = snapshot.config.abilities[ability_id]
        if ability.max_uses is None:
            continue
        player_uses = uses.setdefault(player_id, {})
        player_uses[ability_id] = player_uses.get(ability_id, 0) + 1
    return replace(snapshot, ability_uses=uses)
