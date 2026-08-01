import logging
from datetime import UTC, datetime

import pytest

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.clients.streamlit import operations
from werewolf_agent.clients.streamlit.i18n import load_i18n
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.api import (
    SavedSetupListResponse,
    SavedSetupRevisionListResponse,
    SavedSetupRevisionResponse,
    SavedSetupSummaryResponse,
)
from werewolf_agent.contracts.schemas import (
    AdvanceGameJobResponse,
    AdvanceGameResponse,
    CreateGameRequest,
    GameResponse,
    GameSetupDocumentRequest,
    GameTimelineResponse,
    PlayerObservationResponse,
    PublicGameState,
    PublicPlayerState,
)
from werewolf_agent.observability import (
    bind_observation_context,
    get_observation_context,
)
from werewolf_agent.settings import AppSettings


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
    assert record.llm_model == "fake-list-chat-model"
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
                "phase": "day_discussion",
                "day": 1,
                "me": {
                    "id": player_id,
                    "name": player_id,
                    "status": "alive",
                    "role": "villager",
                },
                "players": [],
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


class _PagingSetupClient:
    def __init__(self) -> None:
        self.setup_offsets: list[int] = []
        self.revision_offsets: list[int] = []

    def list_setups(self, *, limit: int | None = None, offset: int = 0):
        self.setup_offsets.append(offset)
        items = [_setup_summary(offset + 1)]
        return SavedSetupListResponse(
            items=items,
            next_offset=offset + 1 if offset == 0 else None,
        )

    def list_setup_revisions(
        self,
        setup_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ):
        self.revision_offsets.append(offset)
        items = [_setup_revision(offset + 1)]
        return SavedSetupRevisionListResponse(
            items=items,
            next_offset=offset + 1 if offset == 0 else None,
        )


def test_setup_operations_follow_all_bounded_pages(monkeypatch) -> None:
    client = _PagingSetupClient()
    monkeypatch.setattr(operations, "build_streamlit_client", lambda _settings: client)
    settings = AppSettings(_env_file=None)

    setups = operations.list_saved_setups(settings=settings)
    revisions = operations.list_setup_revisions(settings=settings, setup_id="setup-1")

    assert [item.setup_id for item in setups.items] == ["setup-1", "setup-2"]
    assert [item.revision for item in revisions] == [1, 2]
    assert client.setup_offsets == [0, 1]
    assert client.revision_offsets == [0, 1]


def test_setup_page_collection_rejects_non_progressing_cursor() -> None:
    with pytest.raises(AppError):
        operations._collect_bounded_pages(
            lambda _limit, _offset: ([1], 0),
            page_limit=20,
            max_items=100,
        )


def _state(*, status: str, phase: str) -> PublicGameState:
    return PublicGameState(
        game_id="game-1",
        status=status,
        phase=phase,
        day=1,
        version=2,
        players=[
            PublicPlayerState(id="player-1", name="Player 1", alive=True, status="alive"),
            PublicPlayerState(id="player-2", name="Player 2", alive=True, status="alive"),
        ],
        alive_player_ids=["player-1", "player-2"],
        eliminated_player_ids=[],
        winner=None,
        summary={"alive_count": 2},
    )


def _setup_summary(index: int) -> SavedSetupSummaryResponse:
    return SavedSetupSummaryResponse(
        setup_id=f"setup-{index}",
        display_name=f"設定{index}",
        latest_revision=index,
        created_at=_timestamp(),
        updated_at=_timestamp(),
    )


def _setup_revision(revision: int) -> SavedSetupRevisionResponse:
    document = GameSetupDocumentRequest.model_validate(
        build_setup_catalog().require_document("standard_6").to_mapping()
    )
    return SavedSetupRevisionResponse(
        setup_id="setup-1",
        display_name="設定1",
        revision=revision,
        document=document,
        setup_checksum="a" * 64,
        mechanics_checksum="b" * 64,
        created_at=_timestamp(),
    )


def _timestamp() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)
