"""議論PolicyのOutcomeを検証して確定履歴へ適用する."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from werewolf_agent.domain.errors import GameError
from werewolf_agent.domain.rule_packs import DiscussionPolicy
from werewolf_agent.domain.state import (
    Action,
    ActionType,
    DiscussionMove,
    DiscussionPosition,
    DiscussionRelation,
    DiscussionResolution,
    DiscussionResult,
    DiscussionRound,
    DiscussionRoundKind,
    GameEvent,
    GameState,
    SpeechRecord,
    SubmissionMode,
)

_ASCII_CASE_TRANSLATION = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "abcdefghijklmnopqrstuvwxyz",
)


class CoreDiscussionPolicy:
    """独立意見と逆順応答からなる組み込み議論を実装する."""

    def start(self, state: GameState) -> DiscussionRound:
        """日ごとに開始位置を回転させたsealed openingを返す."""
        return _opening_round(state, cycle=1)

    def resolve(
        self,
        state: GameState,
        round_: DiscussionRound,
        submissions: Mapping[str, Action],
    ) -> DiscussionResolution:
        """検証済み提出から公開発言と次roundを返す."""
        if round_.kind is DiscussionRoundKind.OPENING:
            speeches = tuple(
                _speech_record(state, round_, submissions[player_id])
                for player_id in round_.actor_order
                if player_id in submissions and submissions[player_id].type is ActionType.SPEECH
            )
            if not speeches:
                return _after_cycle(state, round_, ())
            response_stage = state.config.discussion.stages[1]
            return DiscussionResolution(
                speeches,
                DiscussionRound(
                    round_id=f"day-{state.day}-cycle-{round_.cycle}-response",
                    cycle=round_.cycle,
                    kind=DiscussionRoundKind.RESPONSE,
                    submission_mode=response_stage.submission_mode,
                    actor_order=tuple(reversed(round_.actor_order)),
                    reference_ids=tuple(speech.speech_id for speech in speeches),
                ),
                False,
            )
        actor_id = round_.current_actor_id
        if actor_id is None:
            raise ValueError("response round has no current actor")
        action = submissions.get(actor_id)
        speeches = (
            (_speech_record(state, round_, action),)
            if action is not None and action.type is ActionType.SPEECH
            else ()
        )
        next_cursor = round_.cursor + 1
        if next_cursor == len(round_.actor_order):
            return _after_cycle(state, round_, speeches)
        return DiscussionResolution(speeches, replace(round_, cursor=next_cursor), False)


def start_discussion(state: GameState, *, policy: DiscussionPolicy) -> DiscussionRound:
    """Policyが返す一日の初期roundをDomain不変条件で検証する."""
    round_ = policy.start(state)
    if not isinstance(round_, DiscussionRound):
        raise TypeError("discussion policy must return DiscussionRound")
    if round_.cycle != 1 or round_.kind is not DiscussionRoundKind.OPENING or round_.cursor != 0:
        raise ValueError("discussion must start from the first opening round")
    if round_.actor_order != _opening_actor_order(state, cycle=1):
        raise ValueError("discussion must start in the configured opening order")
    if round_.round_id in {result.round_id for result in state.history.discussions}:
        raise ValueError("discussion day start requires a fresh round ID")
    return round_


def _opening_round(state: GameState, *, cycle: int) -> DiscussionRound:
    opening_stage = state.config.discussion.stages[0]
    return DiscussionRound(
        round_id=f"day-{state.day}-cycle-{cycle}-opening",
        cycle=cycle,
        kind=DiscussionRoundKind.OPENING,
        submission_mode=opening_stage.submission_mode,
        actor_order=_opening_actor_order(state, cycle=cycle),
    )


def _opening_actor_order(state: GameState, *, cycle: int) -> tuple[str, ...]:
    """Return the configured rotating order for one opening cycle."""
    alive = tuple(player.id for player in state.players.values() if player.is_alive)
    offset = (state.day + cycle - 2) % len(alive)
    return (*alive[offset:], *alive[:offset])


def _after_cycle(
    state: GameState,
    round_: DiscussionRound,
    speeches: tuple[SpeechRecord, ...],
) -> DiscussionResolution:
    next_cycle = round_.cycle + 1
    if next_cycle <= state.config.discussion.cycles_per_day:
        return DiscussionResolution(speeches, _opening_round(state, cycle=next_cycle), False)
    return DiscussionResolution(speeches, None, True)


def record_discussion_submission(
    state: GameState,
    round_: DiscussionRound,
    pending: Mapping[str, Action],
    action: Action,
) -> dict[str, Action]:
    """一つの合法な発言または棄権を未公開bufferへ記録する."""
    if action.type not in {ActionType.SPEECH, ActionType.PASS}:
        raise GameError("Discussion accepts only speech or pass actions.")
    if action.player_id not in round_.actor_order:
        raise GameError("Discussion actor is not eligible for the active round.")
    if action.player_id in pending:
        raise GameError("Discussion action was already submitted.")
    if round_.submission_mode is SubmissionMode.ORDERED and (
        action.player_id != round_.current_actor_id or pending
    ):
        raise GameError("Discussion action does not match the current speaker.")
    if isinstance(action.intent, DiscussionMove):
        if len(action.intent.utterance) > state.config.discussion.message_max_chars:
            raise GameError("Speech message exceeds the configured maximum length.")
        if action.intent.topic_id not in state.players:
            raise GameError("Discussion topic must identify a visible player.")
        if (
            round_.kind is DiscussionRoundKind.OPENING
            and action.intent.topic_id == action.player_id
        ):
            raise GameError("Opening topic must identify another visible player.")
        if round_.kind is DiscussionRoundKind.OPENING and action.intent.response_to_id is not None:
            raise GameError("Opening speech cannot reference another speech.")
        if (
            round_.kind is DiscussionRoundKind.OPENING
            and action.intent.relation not in state.config.discussion.stages[0].allowed_relations
        ):
            raise GameError("Opening discussion move must be independent.")
        if round_.kind is DiscussionRoundKind.OPENING and action.intent.evidence_id is not None:
            _require_public_evidence(state, action.intent.evidence_id)
        if round_.kind is DiscussionRoundKind.RESPONSE and (
            action.intent.response_to_id not in round_.reference_ids
        ):
            raise GameError("Response speech must reference a visible opening speech.")
        if round_.kind is DiscussionRoundKind.RESPONSE:
            referenced = next(
                speech
                for speech in state.history.speeches
                if speech.speech_id == action.intent.response_to_id
            )
            if referenced.player_id == action.player_id:
                raise GameError("Response speech must reference another player's speech.")
            if referenced.topic_id != action.intent.topic_id:
                raise GameError("Response discussion move must inherit the referenced topic.")
            if _normalized_message(referenced.utterance) == _normalized_message(
                action.intent.utterance
            ):
                raise GameError("Response speech must contribute new content.")
            if action.intent.relation not in state.config.discussion.stages[1].allowed_relations:
                raise GameError("Response relation is not allowed by the protocol.")
            _validate_response_relation(state, action.player_id, referenced, action.intent)
        if round_.kind is DiscussionRoundKind.RESPONSE and (
            action.intent.evidence_id != action.intent.response_to_id
        ):
            raise GameError("Response speech must use its referenced speech as evidence.")
    updated = dict(pending)
    updated[action.player_id] = action
    return updated


def resolve_discussion_round(
    state: GameState,
    round_: DiscussionRound,
    submissions: Mapping[str, Action],
    *,
    policy: DiscussionPolicy,
) -> tuple[GameState, DiscussionResolution, list[GameEvent]]:
    """Policy Outcomeを検証し、公開履歴へ原子的に適用する."""
    resolution = policy.resolve(state, round_, submissions)
    _validate_resolution(state, round_, submissions, resolution)
    previously_resolved = {
        speech.player_id for speech in state.history.speeches if speech.round_id == round_.round_id
    }
    previously_resolved.update(
        player_id
        for result in state.history.discussions
        if result.round_id == round_.round_id
        for player_id in result.passed_player_ids
    )
    round_ended = resolution.next_round is None or (
        resolution.next_round.cycle,
        resolution.next_round.kind,
    ) != (round_.cycle, round_.kind)
    implicitly_passed_actor_ids = (
        {round_.current_actor_id}
        if round_.submission_mode is SubmissionMode.ORDERED
        and round_.current_actor_id is not None
        and round_.current_actor_id not in submissions
        else set()
    )
    passed_player_ids = tuple(
        player_id
        for player_id in round_.actor_order
        if (
            submissions.get(player_id) is not None
            and submissions[player_id].type is ActionType.PASS
        )
        or player_id in implicitly_passed_actor_ids
        or (round_ended and player_id not in previously_resolved and player_id not in submissions)
    )
    speech_by_player = {speech.player_id: speech for speech in resolution.speeches}
    actor_ids = tuple(
        player_id
        for player_id in round_.actor_order
        if player_id in speech_by_player or player_id in passed_player_ids
    )
    history = replace(
        state.history,
        speeches=(*state.history.speeches, *resolution.speeches),
        discussions=(
            *state.history.discussions,
            DiscussionResult(
                day=state.day,
                round_id=round_.round_id,
                kind=round_.kind,
                actor_ids=actor_ids,
                speech_ids=tuple(item.speech_id for item in resolution.speeches),
                passed_player_ids=passed_player_ids,
            ),
        ),
    )
    events: list[GameEvent] = []
    for player_id in actor_ids:
        speech = speech_by_player.get(player_id)
        if speech is not None:
            events.append(
                GameEvent(
                    event_type="speech_recorded",
                    phase=state.phase,
                    day=state.day,
                    actor_id=speech.player_id,
                    payload={
                        "speech_id": speech.speech_id,
                        "round_id": speech.round_id,
                        "round_kind": speech.round_kind.value,
                        "utterance": speech.utterance,
                        "topic_id": speech.topic_id,
                        "position": speech.position.value,
                        "relation": speech.relation.value,
                        "evidence_id": speech.evidence_id,
                        "response_to_id": speech.response_to_id,
                    },
                )
            )
        else:
            events.append(
                GameEvent(
                    event_type="discussion_passed",
                    phase=state.phase,
                    day=state.day,
                    actor_id=player_id,
                    payload={
                        "evidence_id": f"pass:{state.day}:{round_.round_id}:{player_id}",
                        "round_id": round_.round_id,
                        "round_kind": round_.kind.value,
                        "topic_id": player_id,
                    },
                )
            )
    return replace(state, history=history), resolution, events


def _speech_record(
    state: GameState,
    round_: DiscussionRound,
    action: Action,
) -> SpeechRecord:
    if not isinstance(action.intent, DiscussionMove):
        raise GameError("Expected a speech action.")
    return SpeechRecord(
        day=state.day,
        speech_id=f"speech:{state.day}:{round_.round_id}:{action.player_id}",
        round_id=round_.round_id,
        round_kind=round_.kind,
        player_id=action.player_id,
        utterance=action.intent.utterance,
        topic_id=action.intent.topic_id,
        position=action.intent.position,
        relation=action.intent.relation,
        evidence_id=action.intent.evidence_id,
        response_to_id=action.intent.response_to_id,
    )


def _normalized_message(value: str) -> str:
    return " ".join(value.split()).translate(_ASCII_CASE_TRANSLATION)


def _validate_response_relation(
    state: GameState,
    actor_id: str,
    referenced: SpeechRecord,
    move: DiscussionMove,
) -> None:
    """参照発言と応答手の立場関係を検証する."""
    if move.relation is DiscussionRelation.INDEPENDENT:
        raise GameError("Response discussion move cannot be independent.")
    if move.relation is DiscussionRelation.ANSWER:
        if referenced.position is not DiscussionPosition.UNDECIDED:
            raise GameError("Answer must reference an undecided opening.")
        if move.position is DiscussionPosition.UNDECIDED:
            raise GameError("Answer must state a position.")
        return
    if move.relation is DiscussionRelation.SUPPORT:
        if move.position is not referenced.position:
            raise GameError("Support must preserve the referenced position.")
        return
    if move.relation is DiscussionRelation.CHALLENGE:
        positions = {move.position, referenced.position}
        if positions != {DiscussionPosition.SUPPORT, DiscussionPosition.OPPOSE}:
            raise GameError("Challenge must state the opposing position.")
        return
    prior = next(
        (
            speech
            for speech in reversed(state.history.speeches)
            if speech.player_id == actor_id and speech.topic_id == move.topic_id
        ),
        None,
    )
    if prior is None or prior.position is move.position:
        raise GameError("Revision must change the actor's prior position on the topic.")


def _require_public_evidence(state: GameState, evidence_id: str) -> None:
    """Evidence IDが確定済みの公開議論事実を指すことを検証する."""
    if any(speech.speech_id == evidence_id for speech in state.history.speeches):
        return
    if any(
        evidence_id == f"pass:{result.day}:{result.round_id}:{player_id}"
        for result in state.history.discussions
        for player_id in result.passed_player_ids
    ):
        return
    raise GameError("Discussion evidence must identify a public discussion fact.")


def _validate_resolution(
    state: GameState,
    round_: DiscussionRound,
    submissions: Mapping[str, Action],
    resolution: DiscussionResolution,
) -> None:
    if not isinstance(resolution, DiscussionResolution):
        raise TypeError("discussion policy must return DiscussionResolution")
    expected_actors = (
        set(round_.actor_order)
        if round_.submission_mode is SubmissionMode.SEALED
        else {round_.current_actor_id}
    )
    if state.config.lifecycle.require_all_actions_before_advance and (
        set(submissions) != expected_actors
    ):
        raise ValueError("discussion submissions do not match the active round")
    if not set(submissions) <= expected_actors:
        raise ValueError("discussion submissions contain an ineligible actor")
    submitted_speeches = {
        action.player_id: action
        for action in submissions.values()
        if action.type is ActionType.SPEECH
    }
    if {speech.player_id for speech in resolution.speeches} != set(submitted_speeches):
        raise ValueError("discussion outcome must preserve submitted speeches")
    for speech in resolution.speeches:
        action = submitted_speeches[speech.player_id]
        expected = _speech_record(state, round_, action)
        if speech != expected:
            raise ValueError("discussion outcome must not alter submitted speech")
    if resolution.next_round is not None:
        same_cycle = resolution.next_round.cycle == round_.cycle
        next_cycle = resolution.next_round.cycle == round_.cycle + 1
        if not same_cycle and not next_cycle:
            raise ValueError("discussion cycle must stay or advance exactly once")
        stage_changed = next_cycle or resolution.next_round.kind is not round_.kind
        used_round_ids = {
            round_.round_id,
            *(result.round_id for result in state.history.discussions),
        }
        if stage_changed and resolution.next_round.round_id in used_round_ids:
            raise ValueError("discussion stage transitions require a fresh round ID")
        if same_cycle:
            if round_.kind is DiscussionRoundKind.OPENING:
                if (
                    resolution.next_round.kind is not DiscussionRoundKind.RESPONSE
                    or resolution.next_round.cursor != 0
                    or resolution.next_round.actor_order != tuple(reversed(round_.actor_order))
                    or set(resolution.next_round.reference_ids)
                    != {speech.speech_id for speech in resolution.speeches}
                ):
                    raise ValueError("discussion opening must advance to its response round")
            elif (
                resolution.next_round.kind is not DiscussionRoundKind.RESPONSE
                or resolution.next_round.round_id != round_.round_id
                or resolution.next_round.cursor != round_.cursor + 1
                or resolution.next_round.actor_order != round_.actor_order
                or resolution.next_round.reference_ids != round_.reference_ids
            ):
                raise ValueError("discussion response cursor must advance exactly once")
        if next_cycle and (
            resolution.next_round.kind is not DiscussionRoundKind.OPENING
            or resolution.next_round.cursor != 0
            or resolution.next_round.actor_order
            != _opening_actor_order(state, cycle=resolution.next_round.cycle)
        ):
            raise ValueError("discussion next cycle must start from opening")
        if next_cycle and not _round_can_end(round_, resolution):
            raise ValueError("discussion cannot advance before the active round is complete")
        if next_cycle and resolution.next_round.cycle > state.config.discussion.cycles_per_day:
            raise ValueError("discussion cannot exceed the configured cycle count")
        if (
            same_cycle
            and round_.kind is DiscussionRoundKind.RESPONSE
            and resolution.next_round.cursor >= len(round_.actor_order)
        ):
            raise ValueError("discussion response cannot continue past its final actor")
    elif not _round_can_end(round_, resolution):
        raise ValueError("discussion cannot complete before the active round is complete")
    elif round_.cycle != state.config.discussion.cycles_per_day:
        raise ValueError("discussion cannot complete before the configured cycle count")


def _round_can_end(
    round_: DiscussionRound,
    resolution: DiscussionResolution,
) -> bool:
    if round_.kind is DiscussionRoundKind.OPENING:
        return not resolution.speeches
    return round_.cursor == len(round_.actor_order) - 1


__all__ = [
    "CoreDiscussionPolicy",
    "record_discussion_submission",
    "resolve_discussion_round",
    "start_discussion",
]
