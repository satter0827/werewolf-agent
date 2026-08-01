"""議論PolicyのOutcomeを検証して確定履歴へ適用する."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from werewolf_agent.domain.errors import GameError
from werewolf_agent.domain.rule_packs import DiscussionPolicy
from werewolf_agent.domain.state import (
    Action,
    ActionType,
    DiscussionResolution,
    DiscussionResult,
    DiscussionRound,
    DiscussionRoundKind,
    GameEvent,
    GameState,
    SpeechIntent,
    SpeechRecord,
    SubmissionMode,
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
            return DiscussionResolution(
                speeches,
                DiscussionRound(
                    round_id=f"day-{state.day}-cycle-{round_.cycle}-response",
                    cycle=round_.cycle,
                    kind=DiscussionRoundKind.RESPONSE,
                    submission_mode=SubmissionMode.ORDERED,
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


def _opening_round(state: GameState, *, cycle: int) -> DiscussionRound:
    alive = tuple(player.id for player in state.players.values() if player.is_alive)
    offset = (state.day + cycle - 2) % len(alive)
    order = (*alive[offset:], *alive[:offset])
    return DiscussionRound(
        round_id=f"day-{state.day}-cycle-{cycle}-opening",
        cycle=cycle,
        kind=DiscussionRoundKind.OPENING,
        submission_mode=SubmissionMode.SEALED,
        actor_order=order,
    )


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
    if isinstance(action.intent, SpeechIntent):
        if len(action.intent.message) > state.config.discussion.message_max_chars:
            raise GameError("Speech message exceeds the configured maximum length.")
        if action.intent.focus_id is not None and (
            action.intent.focus_id not in state.players
            or action.intent.focus_id == action.player_id
        ):
            raise GameError("Speech focus must identify another visible player.")
        if round_.kind is DiscussionRoundKind.OPENING and action.intent.response_to_id is not None:
            raise GameError("Opening speech cannot reference another speech.")
        if round_.kind is DiscussionRoundKind.RESPONSE and (
            action.intent.response_to_id not in round_.reference_ids
        ):
            raise GameError("Response speech must reference a visible opening speech.")
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
    history = replace(
        state.history,
        speeches=(*state.history.speeches, *resolution.speeches),
        discussions=(
            *state.history.discussions,
            DiscussionResult(
                day=state.day,
                round_id=round_.round_id,
                kind=round_.kind,
                speech_ids=tuple(item.speech_id for item in resolution.speeches),
            ),
        ),
    )
    events = [
        GameEvent(
            event_type="speech_recorded",
            phase=state.phase,
            day=state.day,
            actor_id=speech.player_id,
            payload={
                "speech_id": speech.speech_id,
                "round_id": speech.round_id,
                "round_kind": speech.round_kind.value,
                "message": speech.message,
                "focus_id": speech.focus_id,
                "evidence_id": speech.evidence_id,
                "response_to_id": speech.response_to_id,
            },
        )
        for speech in resolution.speeches
    ]
    return replace(state, history=history), resolution, events


def _speech_record(
    state: GameState,
    round_: DiscussionRound,
    action: Action,
) -> SpeechRecord:
    if not isinstance(action.intent, SpeechIntent):
        raise GameError("Expected a speech action.")
    return SpeechRecord(
        day=state.day,
        speech_id=f"speech:{state.day}:{round_.round_id}:{action.player_id}",
        round_id=round_.round_id,
        round_kind=round_.kind,
        player_id=action.player_id,
        message=action.intent.message,
        focus_id=action.intent.focus_id,
        evidence_id=action.intent.evidence_id,
        response_to_id=action.intent.response_to_id,
    )


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
        if same_cycle:
            if round_.kind is DiscussionRoundKind.OPENING:
                if (
                    resolution.next_round.kind is not DiscussionRoundKind.RESPONSE
                    or resolution.next_round.cursor != 0
                    or set(resolution.next_round.reference_ids)
                    != {speech.speech_id for speech in resolution.speeches}
                ):
                    raise ValueError("discussion opening must advance to its response round")
            elif (
                resolution.next_round.kind is not DiscussionRoundKind.RESPONSE
                or resolution.next_round.cursor != round_.cursor + 1
                or resolution.next_round.reference_ids != round_.reference_ids
            ):
                raise ValueError("discussion response cursor must advance exactly once")
        if next_cycle and (
            resolution.next_round.kind is not DiscussionRoundKind.OPENING
            or resolution.next_round.cursor != 0
        ):
            raise ValueError("discussion next cycle must start from opening")
        if set(resolution.next_round.actor_order) != set(round_.actor_order):
            raise ValueError("discussion next round must preserve eligible actors")


__all__ = [
    "CoreDiscussionPolicy",
    "record_discussion_submission",
    "resolve_discussion_round",
]
