"""Visibility-filtered observation rules."""

from __future__ import annotations

from werewolf_agent.domain.rule_packs import AbilityPolicy
from werewolf_agent.domain.rules.action_availability import available_actions, legal_targets
from werewolf_agent.domain.rules.evidence import public_discussion_evidence
from werewolf_agent.domain.rules.player_rules import player_by_id
from werewolf_agent.domain.state import (
    SUPPORTED_FACTIONS,
    AbilityDefinition,
    GameHistory,
    GameState,
    GameView,
    KnowledgeClaim,
    KnowledgeResolution,
    PendingActions,
    Phase,
    Player,
    SpeechRecord,
    VisibleWinResult,
)


def build_player_observation(
    snapshot: GameState,
    pending_actions: PendingActions,
    player_id: str,
    *,
    ability_policy: AbilityPolicy,
) -> GameView:
    """Return the information visible to one player."""
    observer = player_by_id(snapshot, player_id)
    knowledge = ability_policy.resolve_knowledge(snapshot)
    visible_claims = _visible_knowledge_claims(snapshot, player_id, knowledge)
    known_roles = _known_roles(snapshot, player_id, visible_claims)
    known_factions = _known_factions(snapshot, player_id, known_roles, visible_claims)
    actions = tuple(available_actions(snapshot, pending_actions, player_id))
    observed_players = [
        Player(
            id=player.id,
            name=player.name,
            status=player.status,
            role=known_roles.get(player.id),
            eliminated_day=player.eliminated_day,
            killed_night=player.killed_night,
        )
        for player in snapshot.players.values()
    ]
    return GameView(
        phase=snapshot.phase,
        day=snapshot.day,
        me=Player(
            id=observer.id,
            name=observer.name,
            status=observer.status,
            role=observer.role,
            eliminated_day=observer.eliminated_day,
            killed_night=observer.killed_night,
        ),
        players=tuple(observed_players),
        known_roles=known_roles,
        known_factions=known_factions,
        available_actions=actions,
        legal_targets={
            key: tuple(targets)
            for key, targets in legal_targets(snapshot, pending_actions, player_id).items()
        },
        legal_evidence={
            action.key: public_discussion_evidence(snapshot)
            for action in actions
            if action.type.value == "vote"
        },
        history=GameHistory(
            speeches=tuple(
                SpeechRecord(
                    day=speech.day,
                    speech_id=speech.speech_id,
                    round_id=speech.round_id,
                    round_kind=speech.round_kind,
                    player_id=speech.player_id,
                    utterance=speech.utterance,
                    topic_id=speech.topic_id,
                    position=speech.position,
                    relation=speech.relation,
                    evidence_id=speech.evidence_id,
                    response_to_id=speech.response_to_id,
                )
                for speech in snapshot.history.speeches
            ),
            discussions=snapshot.history.discussions,
            votes=snapshot.history.votes,
        ),
        discussion_round=pending_actions.discussion_round,
        win_result=(
            None
            if snapshot.win_result is None
            else VisibleWinResult(
                winner=snapshot.win_result.winner,
                reason=snapshot.win_result.reason,
                day=snapshot.win_result.day,
            )
        ),
    )


def _role_abilities(
    snapshot: GameState, player_id: str, kind: str
) -> list[tuple[str, AbilityDefinition]]:
    player = player_by_id(snapshot, player_id)
    if player.role is None:
        return []
    role = snapshot.config.roles.require_role(player.role)
    return [
        (ability_id, snapshot.config.abilities[ability_id])
        for ability_id in role.abilities
        if snapshot.config.abilities[ability_id].kind == kind
    ]


def _known_roles(
    snapshot: GameState,
    player_id: str,
    knowledge_claims: tuple[KnowledgeClaim, ...],
) -> dict[str, str]:
    observer = player_by_id(snapshot, player_id)
    known: dict[str, str] = {}
    if observer.role is not None:
        known[observer.id] = observer.role

    for claim in knowledge_claims:
        if claim.role is not None:
            known[claim.target_id] = claim.role

    for night in snapshot.history.nights:
        for inspection in night.inspections:
            ability = snapshot.config.abilities[inspection.ability_id]
            if (
                _can_see_ability_result(ability, inspection.player_id, player_id)
                and ability.result_detail == "role"
            ):
                known[inspection.target_id] = inspection.target_role
    if snapshot.config.lifecycle.reveal_role_on_death:
        for player in snapshot.players.values():
            if not player.is_alive and player.role is not None:
                known[player.id] = player.role
    if observer.role is not None:
        known[observer.id] = observer.role
    return known


def _known_factions(
    snapshot: GameState,
    player_id: str,
    known_roles: dict[str, str],
    knowledge_claims: tuple[KnowledgeClaim, ...],
) -> dict[str, str]:
    known = {
        target_id: snapshot.config.roles.faction_for_role(role)
        for target_id, role in known_roles.items()
    }
    for night in snapshot.history.nights:
        for inspection in night.inspections:
            ability = snapshot.config.abilities[inspection.ability_id]
            if _can_see_ability_result(ability, inspection.player_id, player_id):
                known[inspection.target_id] = inspection.target_faction
    for claim in knowledge_claims:
        if claim.faction is not None:
            known[claim.target_id] = claim.faction
    observer = player_by_id(snapshot, player_id)
    if snapshot.config.lifecycle.reveal_role_on_death:
        for player in snapshot.players.values():
            if not player.is_alive and player.role is not None:
                known[player.id] = snapshot.config.roles.faction_for_role(player.role)
    if observer.role is not None:
        known[observer.id] = snapshot.config.roles.faction_for_role(observer.role)
    return known


def resolve_core_knowledge(snapshot: GameState) -> KnowledgeResolution:
    """組み込みknowledge能力の真のroleまたはfaction候補を返す."""
    claims: list[KnowledgeClaim] = []
    for owner in snapshot.players.values():
        if owner.role is None:
            continue
        for ability_id, ability in _role_abilities(snapshot, owner.id, "knowledge"):
            if not _ability_has_started(snapshot, ability):
                continue
            targets: list[Player] = []
            if ability.knowledge_mode == "allies":
                faction = snapshot.config.roles.faction_for_role(owner.role)
                targets = [
                    player
                    for player in snapshot.players.values()
                    if player.role is not None
                    and snapshot.config.roles.faction_for_role(player.role) == faction
                ]
            elif ability.knowledge_mode == "last_eliminated":
                targets = [
                    snapshot.players[vote.eliminated_player_id]
                    for vote in snapshot.history.votes
                    if vote.eliminated_player_id is not None
                    and snapshot.players[vote.eliminated_player_id].role is not None
                ]
            for target in targets:
                if target.role is None:
                    continue
                claims.append(
                    KnowledgeClaim(
                        player_id=owner.id,
                        ability_id=ability_id,
                        target_id=target.id,
                        role=target.role if ability.result_detail == "role" else None,
                        faction=snapshot.config.roles.faction_for_role(target.role)
                        if ability.result_detail == "faction"
                        else None,
                    )
                )
    return KnowledgeResolution(tuple(claims))


def _visible_knowledge_claims(
    snapshot: GameState,
    observer_player_id: str,
    resolution: KnowledgeResolution,
) -> tuple[KnowledgeClaim, ...]:
    """外部knowledge Outcomeを検証し、observerへ見える候補だけを返す."""
    if not isinstance(resolution, KnowledgeResolution):
        raise TypeError("ability policy must return KnowledgeResolution")
    visible: list[KnowledgeClaim] = []
    seen: set[tuple[str, str, str]] = set()
    for claim in resolution.claims:
        owner = player_by_id(snapshot, claim.player_id)
        target = player_by_id(snapshot, claim.target_id)
        if owner.role is None:
            raise ValueError("knowledge owner must have a role")
        role = snapshot.config.roles.require_role(owner.role)
        if claim.ability_id not in role.abilities:
            raise ValueError("knowledge ability must belong to its owner")
        ability = snapshot.config.abilities[claim.ability_id]
        if ability.kind != "knowledge" or not _ability_has_started(snapshot, ability):
            raise ValueError("knowledge ability is not enabled")
        key = (claim.player_id, claim.ability_id, claim.target_id)
        if key in seen:
            raise ValueError("knowledge claim must be unique")
        seen.add(key)
        if ability.result_detail == "role":
            if claim.role is None or claim.faction is not None:
                raise ValueError("role knowledge must contain only a role")
            snapshot.config.roles.require_role(claim.role)
        elif (
            claim.faction not in SUPPORTED_FACTIONS or claim.role is not None or target.role is None
        ):
            raise ValueError("faction knowledge must contain only a configured faction")
        if _can_see_ability_result(
            ability,
            claim.player_id,
            observer_player_id,
        ):
            visible.append(claim)
    return tuple(visible)


def _ability_has_started(snapshot: GameState, ability: AbilityDefinition) -> bool:
    if snapshot.day < ability.start_day:
        return False
    if ability.phase is Phase.NIGHT and snapshot.day == 1 and not ability.enabled_first_night:
        return False
    if snapshot.day > ability.start_day or snapshot.phase is Phase.FINISHED:
        return True
    if ability.phase is Phase.FINISHED:
        return False
    return snapshot.config.phase_order.index(snapshot.phase) >= snapshot.config.phase_order.index(
        ability.phase
    )


def _can_see_ability_result(
    ability: AbilityDefinition,
    owner_player_id: str,
    observer_player_id: str,
) -> bool:
    if ability.result_visibility == "public":
        return True
    return ability.result_visibility == "private" and owner_player_id == observer_player_id
