import ast
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import typer
from typer.testing import CliRunner

from werewolf_agent.contracts import AppError, ErrorCode
from werewolf_agent.interface.cui import commands as cui_commands
from werewolf_agent.interface.cui.app import app
from werewolf_agent.interface.cui.client import HttpGameApiClient
from werewolf_agent.interface.cui.errors import run_app_command
from werewolf_agent.interface.shared.schemas import (
    CreateGameRequest,
    GameEventsResponse,
    GameResponse,
    PublicGameEvent,
    PublicGameState,
    PublicPlayerState,
    StepGameResponse,
)
from werewolf_agent.interface.shared.settings import get_settings


def _state(
    *,
    status: str = "running",
    phase: str = "night",
    winner: str | None = None,
) -> PublicGameState:
    return PublicGameState(
        game_id="game-1",
        status=status,
        phase=phase,
        day=1,
        version=2 if status == "completed" else 1,
        seed=1,
        players=[
            PublicPlayerState(
                id="player-1",
                name="Player 1",
                alive=status != "completed",
                status="dead" if status == "completed" else "alive",
                eliminated_day=1 if status == "completed" else None,
            ),
            PublicPlayerState(id="player-2", name="Player 2", alive=True, status="alive"),
        ],
        alive_player_ids=["player-2"] if status == "completed" else ["player-1", "player-2"],
        eliminated_player_ids=["player-1"] if status == "completed" else [],
        winner=winner,
        summary={"alive_count": 1 if status == "completed" else 2, "speech_count": 0},
    )


def _event(sequence: int, event_type: str, payload: dict[str, object]) -> PublicGameEvent:
    return PublicGameEvent(
        sequence=sequence,
        event_id=uuid4(),
        event_type=event_type,
        phase="finished" if event_type == "game_finished" else "night",
        day=1,
        payload=payload,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class FakeGameApiClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.available_sequence = 0
        self.events = [
            _event(1, "game_started", {"player_count": 6}),
            _event(2, "phase_started", {"phase": "day_discussion"}),
            _event(3, "game_finished", {"winner": "villagers"}),
        ]

    def create_game(self, request: CreateGameRequest) -> GameResponse:
        self.calls.append(("create", request.resolved_player_count))
        self.available_sequence = 1
        return GameResponse(game_id="game-1", state=_state())

    def get_game(self, game_id: str) -> GameResponse:
        self.calls.append(("get", game_id))
        return GameResponse(game_id="game-1", state=_state())

    def step_game(self, game_id: str) -> StepGameResponse:
        self.calls.append(("step", game_id))
        self.available_sequence += 1
        status = "completed" if self.available_sequence >= 3 else "running"
        phase = "finished" if status == "completed" else "day_discussion"
        winner = "villagers" if status == "completed" else None
        events = [event for event in self.events if event.sequence == self.available_sequence]
        return StepGameResponse(
            game_id=game_id,
            status=status,
            state=_state(status=status, phase=phase, winner=winner),
            events=events,
        )

    def list_events(self, game_id: str, *, after: int = 0) -> GameEventsResponse:
        self.calls.append(("events", after))
        events = [
            event for event in self.events if after < event.sequence <= self.available_sequence
        ]
        next_after = events[-1].sequence if events else after
        return GameEventsResponse(game_id=game_id, events=events, next_after=next_after)


def test_doctor_command_succeeds() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Werewolf Agent Doctor" in result.output
    assert "dummy" in result.output


def test_run_app_command_handles_app_error_safely() -> None:
    test_app = typer.Typer()

    def fail() -> None:
        raise AppError(
            "The selected action is not allowed.",
            code=ErrorCode.GAME_INVALID_ACTION,
            context={"api_key": "secret"},
        )

    @test_app.command()
    def broken() -> None:
        run_app_command(fail)

    @test_app.command()
    def ok() -> None:
        pass

    result = CliRunner().invoke(test_app, ["broken"])

    assert result.exit_code == 1
    assert "The selected action is not allowed." in result.output
    assert "secret" not in result.output


def test_doctor_command_reports_invalid_configuration_safely() -> None:
    get_settings.cache_clear()
    try:
        result = CliRunner().invoke(app, ["doctor"], env={"WEREWOLF_LOG_LEVEL": "VERBOSE"})
    finally:
        get_settings.cache_clear()

    assert result.exit_code == 1
    assert "Invalid configuration for WEREWOLF_LOG_LEVEL" in result.output
    assert "log_level must be one of" in result.output


def test_play_command_uses_public_api_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_client = FakeGameApiClient()
    monkeypatch.setattr(cui_commands, "_build_game_api_client", lambda _api_url: fake_client)
    log_path = tmp_path / "events.jsonl"

    result = CliRunner().invoke(
        app,
        [
            "play",
            "--api-url",
            "http://api.test/api/v1",
            "--players",
            "6",
            "--seed",
            "1",
            "--max-steps",
            "4",
            "--log-jsonl",
            str(log_path),
            "--no-show-events",
        ],
    )

    assert result.exit_code == 0
    assert "Game completed" in result.output
    assert fake_client.calls == [
        ("create", 6),
        ("events", 0),
        ("step", "game-1"),
        ("events", 1),
        ("step", "game-1"),
        ("events", 2),
    ]
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert [json_line["sequence"] for json_line in map(json.loads, lines)] == [1, 2, 3]


def test_play_command_handles_api_problem_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingGameApiClient(FakeGameApiClient):
        def create_game(self, request: CreateGameRequest) -> GameResponse:
            _ = request
            raise AppError(
                "game.invalid_action: The selected action is not allowed.",
                code=ErrorCode.GAME_INVALID_ACTION,
                context={"api_key": "secret"},
            )

    monkeypatch.setattr(
        cui_commands,
        "_build_game_api_client",
        lambda _api_url: FailingGameApiClient(),
    )

    result = CliRunner().invoke(app, ["play", "--api-url", "http://api.test/api/v1"])

    assert result.exit_code == 1
    assert "game.invalid_action: The selected action is not allowed." in result.output
    assert "secret" not in result.output


def test_http_client_uses_public_v1_contract_with_mock_transport() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        return httpx.Response(
            200,
            json={"game_id": "game-1", "state": _state().model_dump(mode="json")},
        )

    client = HttpGameApiClient(
        "http://api.test/api/v1",
        transport=httpx.MockTransport(handler),
    )

    response = client.get_game("game-1")

    assert response.game_id == "game-1"
    assert requests == [("GET", "/api/v1/games/game-1")]


def test_cui_does_not_import_internal_game_layers() -> None:
    imported_modules: list[str] = []
    cui_package = Path(cui_commands.__file__).parent
    for source_path in cui_package.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.append(node.module)

    forbidden_prefixes = (
        "werewolf_agent.domain",
        "werewolf_agent.usecase",
    )
    assert not any(module.startswith(forbidden_prefixes) for module in imported_modules)
