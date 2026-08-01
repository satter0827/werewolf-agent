from werewolf_agent.application.definitions import (
    NarrationEventDefinition,
    NarrationProfileDefinition,
)
from werewolf_agent.application.projections import event_to_create
from werewolf_agent.domain import GameEvent
from werewolf_agent.domain.state import Phase
from werewolf_agent.setup._narration import NARRATION_RENDER_MAX_CHARS


def test_public_narration_uses_persisted_theme_terms() -> None:
    profile = NarrationProfileDefinition(
        events={
            "game_finished": NarrationEventDefinition(
                templates=("{phase_label}で{winner_label}の勝利が決まりました。",)
            )
        }
    )
    event = GameEvent(
        event_type="game_finished",
        phase=Phase.FINISHED,
        day=2,
        payload={"winner": "village"},
    )

    created = event_to_create(
        event,
        narration_profile=profile,
        narration_mode="template",
        theme={
            "phase_names": {"finished": "航海終了"},
            "faction_names": {"village": "乗組員陣営"},
        },
    )

    assert created.payload["narration"] == "航海終了で乗組員陣営の勝利が決まりました。"


def test_public_narration_has_a_fox_fallback_label() -> None:
    profile = NarrationProfileDefinition(
        events={
            "game_finished": NarrationEventDefinition(templates=("{winner_label}の勝利です。",))
        }
    )
    event = GameEvent(
        event_type="game_finished",
        phase=Phase.FINISHED,
        day=2,
        payload={"winner": "fox"},
    )

    created = event_to_create(
        event,
        narration_profile=profile,
        narration_mode="template",
    )

    assert created.payload["narration"] == "foxの勝利です。"


def test_public_narration_fails_closed_for_unsafe_or_oversized_output() -> None:
    event = GameEvent(
        event_type="game_started",
        phase=Phase.DAY_DISCUSSION,
        day=1,
        payload={"player_count": 6},
    )
    unsafe = NarrationProfileDefinition(
        events={"game_started": NarrationEventDefinition(templates=("{player_count:1000000}",))}
    )
    oversized = NarrationProfileDefinition(
        events={"game_started": NarrationEventDefinition(templates=("{phase_label}",))}
    )

    assert (
        event_to_create(event, narration_profile=unsafe, narration_mode="template").payload.get(
            "narration"
        )
        is None
    )
    assert (
        event_to_create(
            event,
            narration_profile=oversized,
            narration_mode="template",
            theme={"phase_names": {"day_discussion": "x" * (NARRATION_RENDER_MAX_CHARS + 1)}},
        ).payload.get("narration")
        is None
    )


def test_public_speech_preserves_structured_discussion_identifiers() -> None:
    created = event_to_create(
        GameEvent(
            event_type="speech_recorded",
            phase=Phase.DAY_DISCUSSION,
            day=1,
            actor_id="p1",
            payload={
                "speech_id": "speech:1:opening:p1",
                "round_id": "day-1-cycle-1-opening",
                "round_kind": "opening",
                "utterance": "p2について確認します。",
                "topic_id": "p2",
                "position": "undecided",
                "relation": "independent",
            },
        )
    )

    assert created.payload["speech_id"] == "speech:1:opening:p1"
    assert created.payload["round_id"] == "day-1-cycle-1-opening"
    assert created.payload["round_kind"] == "opening"
