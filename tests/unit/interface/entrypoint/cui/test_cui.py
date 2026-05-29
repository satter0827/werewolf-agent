import ast
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import typer
from typer.testing import CliRunner

from werewolf_agent.commons.configuration import get_settings
from werewolf_agent.contracts import AppError, ErrorCode
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
from werewolf_agent.interface.entrypoint.cui import commands as cui_commands
from werewolf_agent.interface.entrypoint.cui.app import app
from werewolf_agent.interface.entrypoint.cui.client import HttpGameApiClient
from werewolf_agent.interface.entrypoint.cui.errors import run_app_command


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


def _run_summary() -> PublicGameRunSummary:
    return PublicGameRunSummary(
        game_id="game-1",
        status="completed",
        phase="finished",
        day=2,
        version=4,
        seed=1,
        player_count=6,
        alive_count=3,
        winner="villagers",
        step_count=3,
        turn_count=3,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _turn(sequence: int) -> PublicGameTurn:
    return PublicGameTurn(
        sequence=sequence,
        event_sequence=sequence,
        version=2,
        phase="night",
        day=1,
        event_type="phase_started",
        payload={"phase": "night"},
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
        control_tokens = (
            {"player-1": "token"}
            if request.players and request.players[0].agent_type == "human"
            else None
        )
        return GameResponse(game_id="game-1", state=_state(), control_tokens=control_tokens)

    def get_game(self, game_id: str) -> GameResponse:
        self.calls.append(("get", game_id))
        return GameResponse(game_id="game-1", state=_state())

    def health(self) -> dict[str, str]:
        self.calls.append(("health", "ok"))
        return {"status": "ok", "service": "werewolf-agent-api"}

    def get_ruleset(self) -> RulesetResponse:
        self.calls.append(("ruleset", "default"))
        return RulesetResponse(
            id="default",
            name="MVP Default",
            description="default rules",
            player_count={"min": 5, "max": 8},
            roles=[{"id": "villager", "name": "Villager"}],
            phases=[{"id": "night", "name": "Night"}],
            agent_types=[{"id": "llm", "name": "LLM Agent"}],
        )

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

    def list_events(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> GameEventsResponse:
        _ = limit
        self.calls.append(("events", after))
        events = [
            event for event in self.events if after < event.sequence <= self.available_sequence
        ]
        next_after = events[-1].sequence if events else after
        return GameEventsResponse(game_id=game_id, events=events, next_after=next_after)

    def list_games(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> GameRunsResponse:
        self.calls.append(("runs", (status, limit, offset)))
        return GameRunsResponse(runs=[_run_summary()])

    def list_turns(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> GameTurnsResponse:
        self.calls.append(("turns", (game_id, after, limit)))
        return GameTurnsResponse(game_id=game_id, turns=[_turn(1)], next_after=1)

    def get_private_observation(
        self,
        game_id: str,
        player_id: str,
        *,
        control_token: str,
    ) -> PrivateObservationResponse:
        self.calls.append(("observation", (game_id, player_id, control_token)))
        return PrivateObservationResponse(
            game_id=game_id,
            player_id=player_id,
            observation={
                "phase": "day_discussion",
                "day": 1,
                "me": {"id": player_id, "name": "Player 1", "role": "villager"},
                "players": [{"id": "player-1"}, {"id": "player-2"}],
                "known_roles": {"player-1": "villager"},
                "available_actions": ["speech"],
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
        self.calls.append(("action", (game_id, player_id, request.type, control_token)))
        return SubmitPlayerActionResponse(
            game_id=game_id,
            player_id=player_id,
            state=_state(),
            events=[_event(4, "speech_recorded", {"player_id": player_id})],
        )


def test_doctor_command_succeeds() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Werewolf Agent Doctor" in result.output
    assert "fake-list-llm" in result.output


def test_doctor_json_output_is_machine_readable() -> None:
    result = CliRunner().invoke(app, ["doctor", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["provider"] == "fake"
    assert payload["prompt file"] == "packaged"
    assert payload["api url"]


def test_doctor_command_redacts_database_password() -> None:
    get_settings.cache_clear()
    try:
        result = CliRunner().invoke(
            app,
            ["doctor"],
            env={
                "WEREWOLF_DATABASE_URL": (
                    "postgres://werewolf_agent:secret@example.test:5432/werewolf_agent"
                )
            },
        )
    finally:
        get_settings.cache_clear()

    assert result.exit_code == 0
    assert "secret" not in result.output
    assert "[REDACTED]" in result.output


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


def test_play_json_output_is_single_machine_readable_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeGameApiClient()
    monkeypatch.setattr(cui_commands, "_build_game_api_client", lambda _api_url: fake_client)
    get_settings.cache_clear()
    env = {"WEREWOLF_LOG_LEVEL": "CRITICAL"}

    try:
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
                "--output",
                "json",
            ],
            env=env,
        )
    finally:
        get_settings.cache_clear()

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["game_id"] == "game-1"
    assert payload["winner"] == "villagers"
    assert [event["sequence"] for event in payload["events"]] == [1, 2, 3]


def test_create_command_can_request_one_human_player(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = FakeGameApiClient()
    monkeypatch.setattr(cui_commands, "_build_game_api_client", lambda _api_url: fake_client)

    result = CliRunner().invoke(
        app,
        [
            "create",
            "--api-url",
            "http://api.test/api/v1",
            "--players",
            "5",
            "--human-player",
            "player-1",
            "--role-count",
            "werewolf=1",
            "--role-count",
            "villager=4",
        ],
    )

    assert result.exit_code == 0
    assert "control token" in result.output
    assert fake_client.calls == [("create", 5)]


def test_create_command_rejects_unknown_human_player() -> None:
    result = CliRunner().invoke(
        app,
        ["create", "--players", "5", "--human-player", "player-9"],
    )

    assert result.exit_code == 1
    assert "human_player must match a generated player id" in result.output


def test_ruleset_state_and_step_commands_use_public_api_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeGameApiClient()
    monkeypatch.setattr(cui_commands, "_build_game_api_client", lambda _api_url: fake_client)

    ruleset_result = CliRunner().invoke(app, ["ruleset", "--api-url", "http://api.test/api/v1"])
    state_result = CliRunner().invoke(
        app, ["state", "game-1", "--api-url", "http://api.test/api/v1"]
    )
    step_result = CliRunner().invoke(app, ["step", "game-1", "--api-url", "http://api.test/api/v1"])

    assert ruleset_result.exit_code == 0
    assert state_result.exit_code == 0
    assert step_result.exit_code == 0
    assert ("ruleset", "default") in fake_client.calls
    assert ("get", "game-1") in fake_client.calls
    assert ("step", "game-1") in fake_client.calls


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


def test_watch_replay_runs_and_turns_use_public_api_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_client = FakeGameApiClient()
    fake_client.available_sequence = 3
    monkeypatch.setattr(cui_commands, "_build_game_api_client", lambda _api_url: fake_client)
    log_path = tmp_path / "watch.jsonl"
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(_event(1, "game_started", {"player_count": 6}).model_dump_json())

    watch_result = CliRunner().invoke(
        app,
        ["watch", "game-1", "--api-url", "http://api.test/api/v1", "--log-jsonl", str(log_path)],
    )
    replay_result = CliRunner().invoke(app, ["replay", "--events", str(events_path)])
    runs_result = CliRunner().invoke(app, ["runs", "--api-url", "http://api.test/api/v1"])
    turns_result = CliRunner().invoke(
        app,
        ["turns", "game-1", "--api-url", "http://api.test/api/v1"],
    )

    assert watch_result.exit_code == 0
    assert replay_result.exit_code == 0
    assert runs_result.exit_code == 0
    assert turns_result.exit_code == 0
    assert "Game Runs" in runs_result.output
    assert "Game Turns" in turns_result.output
    assert log_path.exists()


def test_watch_follow_rejects_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = FakeGameApiClient()
    monkeypatch.setattr(cui_commands, "_build_game_api_client", lambda _api_url: fake_client)

    result = CliRunner().invoke(
        app,
        [
            "watch",
            "game-1",
            "--api-url",
            "http://api.test/api/v1",
            "--follow",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 1
    assert "Use jsonl output when following streamed events." in result.output


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
