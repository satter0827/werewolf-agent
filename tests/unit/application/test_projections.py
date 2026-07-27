from werewolf_agent.application.definitions import (
    NarrationEventDefinition,
    NarrationProfileDefinition,
)
from werewolf_agent.application.projections import event_to_create
from werewolf_agent.domain import GameEvent
from werewolf_agent.domain.state import Phase


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
