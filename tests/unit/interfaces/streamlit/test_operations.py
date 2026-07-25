import logging
from datetime import UTC, datetime

from werewolf_agent.configuration import AppSettings
from werewolf_agent.contracts.schemas import (
    AdvanceGameJobResponse,
    AdvanceGameResponse,
    CreateGameRequest,
    GameResponse,
    GameTimelineResponse,
    LocalRulesSettings,
    PlayerObservationResponse,
    PublicGameState,
    PublicPlayerState,
)
from werewolf_agent.interfaces.streamlit import operations
from werewolf_agent.interfaces.streamlit.i18n import load_i18n
from werewolf_agent.observability import (
    bind_observation_context,
    get_observation_context,
)


def test_streamlit_rerun_startup_log_includes_runtime_paths(
    tmp_path,
    caplog,
) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path,
        log_level="DEBUG",
        log_output="both",
        log_third_party_level="INFO",
    )

    with caplog.at_level(logging.DEBUG, logger=operations.__name__):
        operations.log_streamlit_rerun_started(settings)

    record = next(
        record for record in caplog.records if record.event_action == "streamlit.rerun.started"
    )
    assert record.event_outcome == "success"
    assert record.data_source == "supabase"
    assert record.log_level == "DEBUG"
    assert record.log_output == "both"
    assert record.log_file_path == str(settings.log_file_path)
    assert record.log_third_party_level == "INFO"
    assert record.llm_provider == "fake"
    assert record.llm_model == "fake-list-llm"
    assert record.llm_base_url == "provider default"
    assert not hasattr(record, "seat_credential")


class FakeStreamlitClient:
    def __init__(self) -> None:
        self.stepped = False
        self.created_request: CreateGameRequest | None = None
        self.advance_context: dict[str, str] = {}

    def create_game(self, request: CreateGameRequest) -> GameResponse:
        self.created_request = request
        return GameResponse(game_id="game-1", state=_state(status="running", phase="night"))

    def get_game(self, game_id: str) -> GameResponse:
        phase = "finished" if self.stepped else "day_discussion"
        status = "completed" if self.stepped else "running"
        return GameResponse(game_id=game_id, state=_state(status=status, phase=phase))

    def get_timeline(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> GameTimelineResponse:
        _ = after, limit
        return GameTimelineResponse(game_id=game_id, items=[], next_after=0)

    def get_private_observation(
        self,
        game_id: str,
        player_id: str,
    ) -> PlayerObservationResponse:
        return PlayerObservationResponse(
            game_id=game_id,
            player_id=player_id,
            observation={
                "me": {"id": player_id, "role": "villager"},
                "known_roles": {},
                "available_actions": [],
            },
        )

    def advance_game(self, game_id: str) -> AdvanceGameResponse:
        self.advance_context = get_observation_context()
        self.stepped = True
        return AdvanceGameResponse(
            game_id=game_id,
            status="completed",
            state=_state(status="completed", phase="finished"),
            timeline=[],
        )

    def start_advance_game(self, game_id: str) -> AdvanceGameJobResponse:
        self.advance_context = get_observation_context()
        return AdvanceGameJobResponse(
            job_id="job-1",
            game_id=game_id,
            status="queued",
            state_version=2,
            poll_url="/api/v1/games/game-1/advance-jobs/job-1",
            created_at=_timestamp(),
            updated_at=_timestamp(),
        )

    def get_advance_job(self, game_id: str, job_id: str) -> AdvanceGameJobResponse:
        return AdvanceGameJobResponse(
            job_id=job_id,
            game_id=game_id,
            status="completed",
            state_version=2,
            result=AdvanceGameResponse(
                game_id=game_id,
                status="completed",
                state=_state(status="completed", phase="finished"),
                timeline=[],
            ),
            created_at=_timestamp(),
            updated_at=_timestamp(),
        )


def test_advance_one_step_logs_public_step_without_private_context(
    monkeypatch,
    caplog,
) -> None:
    client = FakeStreamlitClient()
    monkeypatch.setattr(operations, "build_streamlit_client", lambda *_args, **_kwargs: client)
    settings = AppSettings(_env_file=None)

    with caplog.at_level(logging.DEBUG, logger=operations.__name__):
        operations.advance_one_step(
            settings=settings,
            game_id="game-1",
        )

    assert client.stepped is True
    assert client.advance_context["trace_id"]
    actions = [record.event_action for record in caplog.records]
    assert "streamlit.advance_step.started" in actions
    completed = next(
        record
        for record in caplog.records
        if record.event_action == "streamlit.advance_step.completed"
    )
    assert completed.game_phase == "finished"
    assert not hasattr(completed, "seat_credential")


def test_advance_one_step_reuses_existing_trace_context(
    monkeypatch,
) -> None:
    client = FakeStreamlitClient()
    monkeypatch.setattr(operations, "build_streamlit_client", lambda *_args, **_kwargs: client)
    settings = AppSettings(_env_file=None)

    with bind_observation_context(trace_id="trace-existing"):
        operations.advance_one_step(
            settings=settings,
            game_id="game-1",
        )

    assert client.advance_context["trace_id"] == "trace-existing"


def test_start_advance_step_returns_job_with_trace_context(monkeypatch) -> None:
    client = FakeStreamlitClient()
    monkeypatch.setattr(operations, "build_streamlit_client", lambda *_args, **_kwargs: client)
    settings = AppSettings(_env_file=None)

    job = operations.start_advance_step(
        settings=settings,
        game_id="game-1",
    )

    assert job.job_id == "job-1"
    assert client.advance_context["trace_id"]


def test_create_game_from_setup_builds_role_count_request(monkeypatch, caplog) -> None:
    client = FakeStreamlitClient()
    monkeypatch.setattr(operations, "build_streamlit_client", lambda *_args, **_kwargs: client)
    settings = AppSettings(_env_file=None)
    rules = _rules()

    with caplog.at_level(logging.INFO, logger=operations.__name__):
        created = operations.create_game_from_setup(
            settings=settings,
            role_counts={"werewolf": 1, "villager": 4},
            rules=rules,
            seed_text="7",
            manual_player_id="player-1",
            scenario_id="classic_village",
            setup_preset_id="standard_6",
            agent_strategy_id="role_basic",
            narration_mode="standard",
            character_assignments={},
            custom_roles=[],
            custom_characters=[],
        )

    assert created.game_id == "game-1"
    assert client.created_request is not None
    assert client.created_request.role_counts == {"werewolf": 1, "villager": 4}
    assert client.created_request.manual_player_id == "player-1"
    assert client.created_request.seed == 7
    assert client.created_request.rules == rules
    assert client.created_request.scenario_id == "classic_village"
    assert client.created_request.agent_strategy_id == "role_basic"
    record = next(
        record for record in caplog.records if record.event_action == "streamlit.game.created"
    )
    assert record.player_count == 2
    assert not hasattr(record, "seat_credential")


def test_observer_screen_uses_public_data_without_private_observation(monkeypatch) -> None:
    client = FakeStreamlitClient()
    monkeypatch.setattr(operations, "build_streamlit_client", lambda *_args, **_kwargs: client)
    settings = AppSettings(_env_file=None)
    catalog = load_i18n(settings)

    screen = operations.load_game_screen(
        settings=settings,
        game_id="game-1",
        manual_player_id=None,
        screen_mode="observer",
        catalog=catalog,
        lang="ja",
    )

    assert screen.screen_mode == "observer"
    assert screen.observation is None
    assert screen.observer_log is not None
    assert screen.observer_log.entries == []


def _state(*, status: str, phase: str) -> PublicGameState:
    return PublicGameState(
        game_id="game-1",
        status=status,
        phase=phase,
        day=1,
        version=2,
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


def _timestamp() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)


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
