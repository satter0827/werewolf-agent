from datetime import UTC, datetime

from werewolf_agent.clients.streamlit.history import (
    build_history_options,
    create_session_game_selection,
)
from werewolf_agent.clients.streamlit.i18n import load_i18n
from werewolf_agent.contracts.schemas import (
    GameResponse,
    LocalRulesSettings,
    PublicGameState,
    PublicGameSummary,
    PublicPlayerState,
)
from werewolf_agent.settings import AppSettings


def test_session_game_selection_can_be_opened_as_playable_without_disk_save() -> None:
    settings = AppSettings(_env_file=None)
    catalog = load_i18n(settings)
    response = GameResponse(game_id="game-1", state=_state())
    selection = create_session_game_selection(
        response,
        manual_player_id="player-1",
        role_counts={"werewolf": 1, "villager": 4},
        rules=_rules(),
        seed=1,
        scenario_id="classic_village",
        setup_preset_id="standard_6",
        agent_strategy_id="stable_fast",
        narration_mode="standard",
        character_assignments={},
        custom_roles=[],
        custom_characters=[],
    )

    options = build_history_options(
        selection,
        [_summary("game-1")],
        catalog=catalog,
        lang="ja",
    )

    assert options[0].option_id.startswith("session:")
    assert options[0].mode == "playable"
    assert options[0].manual_player_id == "player-1"
    assert options[0].agent_strategy_id == "stable_fast"


def test_database_history_without_session_token_is_observer_only() -> None:
    settings = AppSettings(_env_file=None)
    catalog = load_i18n(settings)

    options = build_history_options(
        None,
        [_summary("game-2")],
        catalog=catalog,
        lang="ja",
    )

    assert options[0].option_id == "game:game-2"
    assert options[0].mode == "observer"


def _summary(game_id: str) -> PublicGameSummary:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return PublicGameSummary(
        game_id=game_id,
        status="completed",
        phase="finished",
        day=2,
        version=4,
        seed=1,
        player_count=5,
        alive_count=3,
        winner="villagers",
        step_count=3,
        turn_count=3,
        created_at=now,
        updated_at=now,
        completed_at=now,
    )


def _state() -> PublicGameState:
    return PublicGameState(
        game_id="game-1",
        status="running",
        phase="night",
        day=1,
        version=1,
        seed=1,
        players=[
            PublicPlayerState(id="player-1", name="Player 1", alive=True, status="alive"),
            PublicPlayerState(id="player-2", name="Player 2", alive=True, status="alive"),
        ],
        alive_player_ids=["player-1", "player-2"],
        eliminated_player_ids=[],
        winner=None,
        summary={"alive_count": 2},
    )


def _rules() -> LocalRulesSettings:
    return LocalRulesSettings(
        day_speech_limit_per_player=1,
        allow_self_vote=False,
        allow_vote_revision=False,
        allow_night_action_revision=False,
        enable_first_night_attack=True,
        enable_no_elimination_on_tie=True,
        enable_random_elimination_on_tie=False,
        allow_knight_self_guard=True,
        allow_knight_repeat_guard=True,
        allow_seer_self_inspect=False,
        allow_werewolf_friendly_fire=False,
        reveal_role_on_death=False,
    )
