import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from werewolf_agent.contracts.schemas import (
    CreateGameRequest,
    GameEventsResponse,
    GameResponse,
    GameRunsResponse,
    GameTurnsResponse,
    PrivateObservationResponse,
    PublicGameEvent,
    PublicGameRunSummary,
    PublicGameState,
    PublicGameTurn,
    PublicPlayerState,
    RulesetResponse,
    StepGameResponse,
    SubmitPlayerActionRequest,
    SubmitPlayerActionResponse,
)
from werewolf_agent.interface.entrypoint.streamlit.i18n import normalize_language, text

ROOT = Path(__file__).resolve().parents[5]
APP_TEST_TMP = ROOT / ".werewolf-agent" / "cache" / "streamlit-app-test"
APP_TEST_TMP.mkdir(parents=True, exist_ok=True)
os.environ["TEMP"] = str(APP_TEST_TMP)
os.environ["TMP"] = str(APP_TEST_TMP)
tempfile.tempdir = str(APP_TEST_TMP)

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
app_test_module = pytest.importorskip("streamlit.testing.v1.app_test")
if hasattr(app_test_module.TMP_DIR, "_finalizer"):
    app_test_module.TMP_DIR._finalizer.detach()
app_test_module.TMP_DIR = SimpleNamespace(name=str(APP_TEST_TMP))

_FAKE_APP_SCRIPT = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})

from tests.unit.interface.entrypoint.streamlit.test_streamlit_app import FakeGameApiClient
from werewolf_agent.commons.configuration import AppSettings
from werewolf_agent.interface.entrypoint.streamlit import app as streamlit_app

fake_client = FakeGameApiClient()
settings = AppSettings(
    _env_file=None,
    log_output="none",
    streamlit_api_url="http://api.test/api/v1",
)
streamlit_app.render_app(
    settings=settings,
    client_factory=lambda _api_url, _timeout: fake_client,
)
"""


def _record_call(name: str) -> None:
    import streamlit as st

    st.session_state[name] = int(st.session_state.get(name, 0)) + 1


def _button(app_test: AppTest, label: str):
    return next(item for item in app_test.button if item.label == label)


def _checkbox(app_test: AppTest, label: str):
    return next(item for item in app_test.checkbox if item.label == label)


def _text_input(app_test: AppTest, label: str):
    return next(item for item in app_test.text_input if item.label == label)


def _text_area(app_test: AppTest, label: str):
    return next(item for item in app_test.text_area if item.label == label)


def _state() -> PublicGameState:
    return PublicGameState(
        game_id="game-1",
        status="running",
        phase="day_discussion",
        day=1,
        version=1,
        seed=1,
        players=[
            PublicPlayerState(id="player-1", name="Player 1", alive=True, status="alive"),
            PublicPlayerState(id="player-2", name="Player 2", alive=True, status="alive"),
        ],
        alive_player_ids=["player-1", "player-2"],
        eliminated_player_ids=[],
        summary={"alive_count": 2},
    )


def _event(sequence: int = 1) -> PublicGameEvent:
    return PublicGameEvent(
        sequence=sequence,
        event_id=uuid4(),
        event_type="game_started",
        phase="day_discussion",
        day=1,
        payload={"player_count": 2},
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _run_summary() -> PublicGameRunSummary:
    return PublicGameRunSummary(
        game_id="game-1",
        status="running",
        phase="day_discussion",
        day=1,
        version=1,
        seed=1,
        player_count=2,
        alive_count=2,
        step_count=0,
        turn_count=1,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _turn() -> PublicGameTurn:
    return PublicGameTurn(
        sequence=1,
        event_sequence=1,
        version=1,
        phase="day_discussion",
        day=1,
        event_type="game_started",
        payload={},
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class FakeGameApiClient:
    def __init__(self) -> None:
        self.created = False
        self.stepped = False

    def health(self) -> dict[str, str]:
        return {"status": "ok"}

    def get_ruleset(self) -> RulesetResponse:
        return RulesetResponse(
            id="default",
            name="Default",
            description="Default rules",
            player_count={"min": 2, "max": 8},
            roles=[],
            phases=[],
            agent_types=[],
        )

    def create_game(self, request: CreateGameRequest) -> GameResponse:
        self.created = True
        _record_call("create_calls")
        control_tokens = (
            {"player-1": "token"}
            if request.players and request.players[0].agent_type == "human"
            else None
        )
        return GameResponse(game_id="game-1", state=_state(), control_tokens=control_tokens)

    def get_game(self, game_id: str) -> GameResponse:
        return GameResponse(game_id=game_id, state=_state())

    def list_games(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> GameRunsResponse:
        _ = (status, limit, offset)
        return GameRunsResponse(runs=[_run_summary()])

    def step_game(self, game_id: str) -> StepGameResponse:
        self.stepped = True
        _record_call("step_calls")
        return StepGameResponse(
            game_id=game_id,
            status="running",
            state=_state(),
            events=[_event(2)],
        )

    def list_events(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> GameEventsResponse:
        _ = (after, limit)
        return GameEventsResponse(game_id=game_id, events=[_event()], next_after=1)

    def list_turns(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> GameTurnsResponse:
        _ = (after, limit)
        return GameTurnsResponse(game_id=game_id, turns=[_turn()], next_after=1)

    def get_private_observation(
        self,
        game_id: str,
        player_id: str,
        *,
        control_token: str,
    ) -> PrivateObservationResponse:
        _record_call("observation_calls")
        return PrivateObservationResponse(
            game_id=game_id,
            player_id=player_id,
            observation={
                "available_actions": ["speech"],
                "me": {"id": player_id, "role": "villager"},
            },
        )

    def submit_player_action(
        self,
        game_id: str,
        player_id: str,
        request: SubmitPlayerActionRequest,
        *,
        control_token: str,
    ) -> SubmitPlayerActionResponse:
        _ = (request, control_token)
        _record_call("action_calls")
        return SubmitPlayerActionResponse(
            game_id=game_id,
            player_id=player_id,
            state=_state(),
            events=[_event(3)],
        )


def test_i18n_defaults_to_japanese_and_supports_english() -> None:
    assert normalize_language("fr") == "ja"
    assert text("ja", "create_game") == "ゲーム作成"
    assert text("en", "create_game") == "Create Game"


def test_streamlit_app_renders_console_with_fake_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(app_test_module, "TMP_DIR", SimpleNamespace(name=str(tmp_path)))
    app_test = AppTest.from_string(_FAKE_APP_SCRIPT)
    app_test.run(timeout=10)

    assert not app_test.exception
    assert app_test.title[0].value == "Werewolf Agent Console"
    assert [tab.label for tab in app_test.tabs] == [
        "タイムライン",
        "イベント",
        "人間操作",
        "実行履歴",
    ]
    assert app_test.success[0].value == "接続済み"

    _button(app_test, "1ステップ進める").click().run(timeout=10)
    assert not app_test.exception
    assert app_test.session_state["step_calls"] == 1

    _checkbox(app_test, "人間プレイヤーを含める").set_value(True).run(timeout=10)
    _button(app_test, "ゲーム作成").click().run(timeout=10)
    assert not app_test.exception
    assert app_test.session_state["create_calls"] == 1
    assert app_test.session_state["control_tokens"] == {"player-1": "token"}

    _text_input(app_test, "Control token").set_value("token").run(timeout=10)
    _button(app_test, "Observation を取得").click().run(timeout=10)
    assert not app_test.exception
    assert app_test.session_state["observation_calls"] == 1

    _text_area(app_test, "メッセージ").set_value("hello").run(timeout=10)
    _button(app_test, "アクション送信").click().run(timeout=10)
    assert not app_test.exception
    assert app_test.session_state["action_calls"] == 1


def test_streamlit_app_can_switch_language_to_english(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(app_test_module, "TMP_DIR", SimpleNamespace(name=str(tmp_path)))
    app_test = AppTest.from_string(_FAKE_APP_SCRIPT)
    app_test.run(timeout=10)
    language_selectbox = next(item for item in app_test.selectbox if item.label == "言語")
    language_selectbox.set_value("English").run(timeout=10)

    assert not app_test.exception
    assert app_test.title[0].value == "Werewolf Agent Console"
    updated_language_selectbox = next(
        item for item in app_test.selectbox if item.label in {"言語", "Language"}
    )
    assert updated_language_selectbox.value == "English"
    assert any(tab.label == "Timeline" for tab in app_test.tabs)
