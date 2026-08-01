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
from werewolf_agent.domain.rule_packs import AbilityPolicy
from werewolf_agent.domain.rules.observations import resolve_core_knowledge
from werewolf_agent.domain.rules.player_rules import (
    faction_for_role,
    mark_dead,
    player_by_id,
    require_alive,
    require_phase,
    resolve_core_death_reactions,
    resolve_death_reactions,
)
from werewolf_agent.domain.state import (
    AbilityDefinition,
    Action,
    ActionType,
    DeathReactionResolution,
    GameState,
    InspectionResult,
    KnowledgeResolution,
    NightResolution,
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
    *,
    policy: AbilityPolicy,
) -> tuple[GameState, NightResult]:
    """PolicyのOutcomeを検証し、Domain stateへatomicに適用する."""
    require_phase(snapshot, Phase.NIGHT)
    random_state = rng.getstate()
    try:
        resolution = policy.resolve_night(snapshot, pending_actions, rng)
        _validate_resolution(snapshot, pending_actions, resolution)
        return _apply_night_resolution(
            snapshot,
            pending_actions,
            resolution,
            rng,
            policy=policy,
        )
    except Exception:
        rng.setstate(random_state)
        raise


def _apply_night_resolution(
    snapshot: GameState,
    pending_actions: Mapping[str, Action],
    resolution: NightResolution,
    rng: random.Random,
    *,
    policy: AbilityPolicy,
) -> tuple[GameState, NightResult]:
    """検証済み夜Outcomeと死亡反応を一つのstate遷移へ適用する."""
    updated_snapshot = snapshot
    for player_id in sorted(resolution.killed_player_ids):
        updated_snapshot = mark_dead(updated_snapshot, player_id, killed_night=snapshot.day)
    updated_snapshot, reaction_deaths = resolve_death_reactions(
        updated_snapshot,
        sorted(resolution.killed_player_ids),
        rng,
        policy=policy,
        during_night=True,
    )
    killed_ids = tuple(sorted((*resolution.killed_player_ids, *reaction_deaths)))
    ordered = _ordered_ability_actions(snapshot, pending_actions)
    updated_snapshot = _consume_limited_abilities(
        updated_snapshot,
        ordered,
        passive_uses=resolution.passive_uses,
    )
    result = NightResult(
        day=snapshot.day,
        attacked_player_id=resolution.attacked_player_ids[0]
        if resolution.attacked_player_ids
        else None,
        protected_player_id=resolution.protected_player_ids[0]
        if resolution.protected_player_ids
        else None,
        killed_player_id=killed_ids[0] if killed_ids else None,
        killed_player_ids=killed_ids,
        inspections=resolution.inspections,
        ability_targets={
            action.player_id: {action.ability_id: _target(action)}
            for action in ordered
            if action.ability_id is not None
        },
    )
    history = replace(updated_snapshot.history, nights=(*updated_snapshot.history.nights, result))
    return replace(updated_snapshot, history=history), result


class CoreAbilityPolicy:
    """組み込みの夜能力と受動耐性の解決意味論を実装する."""

    def resolve_night(
        self,
        state: GameState,
        pending_actions: Mapping[str, Action],
        random: random.Random,
    ) -> NightResolution:
        """設定済み能力を優先順位順に解決してOutcomeを返す."""
        ordered = _ordered_ability_actions(state, pending_actions)
        return _resolve_core_night(state, ordered, random)

    def resolve_death_reactions(
        self,
        state: GameState,
        newly_dead_player_ids: tuple[str, ...],
        random: random.Random,
    ) -> DeathReactionResolution:
        """組み込みの死亡反応連鎖をstate変更なしで解決する."""
        return resolve_core_death_reactions(state, newly_dead_player_ids, random)

    def resolve_knowledge(self, state: GameState) -> KnowledgeResolution:
        """組み込みknowledge能力の知識候補を返す."""
        return resolve_core_knowledge(state)


def _ordered_ability_actions(
    snapshot: GameState,
    pending_actions: Mapping[str, Action],
) -> list[Action]:
    """能動能力を設定済み優先順位で安定して並べる."""
    ability_actions = [
        action for action in pending_actions.values() if action.type is ActionType.USE_ABILITY
    ]
    return sorted(
        ability_actions,
        key=lambda action: (
            _ability_for_action(snapshot, action).resolution_priority,
            action.ability_id or "",
            action.player_id,
        ),
    )


def _resolve_core_night(
    snapshot: GameState,
    ordered: list[Action],
    rng: random.Random,
) -> NightResolution:
    """組み込み能力のOutcomeをstate変更なしで計算する."""
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
                pending_uses=passive_uses,
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
                    pending_uses=passive_uses,
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
                    pending_uses=passive_uses,
                )
                if vulnerability_id is not None:
                    passive_uses.append((inspection.target_id, vulnerability_id))
                    immunity_id = _eligible_passive(
                        snapshot,
                        inspection.target_id,
                        "immunity",
                        source_kind="inspect",
                        pending_uses=passive_uses,
                    )
                    if immunity_id is not None:
                        passive_uses.append((inspection.target_id, immunity_id))
                    else:
                        killed_player_ids.add(inspection.target_id)

    return NightResolution(
        attacked_player_ids=tuple(attacked_player_ids),
        protected_player_ids=tuple(sorted(protected_player_ids)),
        killed_player_ids=tuple(sorted(killed_player_ids)),
        inspections=tuple(inspection_results),
        passive_uses=tuple(passive_uses),
    )


def _validate_resolution(
    snapshot: GameState,
    pending_actions: Mapping[str, Action],
    resolution: NightResolution,
) -> None:
    """外部PolicyのOutcomeがDomain invariantを満たすことを検証する."""
    if not isinstance(resolution, NightResolution):
        raise TypeError("ability policy must return NightResolution")
    for label, player_ids in (
        ("attacked", resolution.attacked_player_ids),
        ("protected", resolution.protected_player_ids),
        ("killed", resolution.killed_player_ids),
    ):
        if len(set(player_ids)) != len(player_ids):
            raise ValueError(f"{label} player ids must be unique")
        for player_id in player_ids:
            require_alive(snapshot, player_id)
    submitted = {
        (action.player_id, action.ability_id)
        for action in pending_actions.values()
        if action.type is ActionType.USE_ABILITY
    }
    for inspection in resolution.inspections:
        if inspection.day != snapshot.day:
            raise ValueError("inspection day must match current day")
        require_alive(snapshot, inspection.player_id)
        require_alive(snapshot, inspection.target_id)
        if (inspection.player_id, inspection.ability_id) not in submitted:
            raise ValueError("inspection must correspond to a submitted ability")
        ability = snapshot.config.abilities.get(inspection.ability_id)
        if ability is None or ability.kind != "inspect":
            raise ValueError("inspection ability must be configured as inspect")
        if not inspection.target_role or not inspection.target_faction:
            raise ValueError("inspection result must be nonblank")
    passive_use_counts = Counter(resolution.passive_uses)
    for (player_id, ability_id), outcome_uses in passive_use_counts.items():
        player = require_alive(snapshot, player_id)
        if player.role is None:
            raise ValueError("passive ability owner must have a role")
        role = snapshot.config.roles.require_role(player.role)
        if ability_id not in role.abilities:
            raise ValueError("passive ability must belong to its owner")
        ability = snapshot.config.abilities[ability_id]
        if ability.kind not in {"immunity", "vulnerability"}:
            raise ValueError("night passive use must be immunity or vulnerability")
        used = snapshot.ability_uses.get(player_id, {}).get(ability_id, 0)
        if ability.max_uses is not None and used + outcome_uses > ability.max_uses:
            raise ValueError("passive ability outcome exceeds max uses")
        if (
            ability.phase is not snapshot.phase
            or snapshot.day < ability.start_day
            or (snapshot.day == 1 and not ability.enabled_first_night)
        ):
            raise ValueError("passive ability is not enabled")


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
    pending_uses: Iterable[tuple[str, str]] = (),
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
        used = snapshot.ability_uses.get(player_id, {}).get(ability_id, 0) + sum(
            pending_player_id == player_id and pending_ability_id == ability_id
            for pending_player_id, pending_ability_id in pending_uses
        )
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


__all__ = ["CoreAbilityPolicy", "record_night_action", "resolve_night"]
