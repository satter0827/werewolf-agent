from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from werewolf_agent.commons.configuration import AppSettings
from werewolf_agent.commons.observability import bind_observation_context
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.schemas import (
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
    SubmitPlayerActionRequest,
    SubmitPlayerActionResponse,
)
from werewolf_agent.interface.shared import workflows
from werewolf_agent.interface.shared.api_client import HttpGameApiClient
from werewolf_agent.interface.shared.diagnostics import build_interface_diagnostics
from werewolf_agent.interface.shared.game_requests import build_create_game_request


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


def _event() -> PublicGameEvent:
    return PublicGameEvent(
        sequence=1,
        event_id=uuid4(),
        event_type="game_started",
        phase="day_discussion",
        day=1,
        payload={"player_count": 2},
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class FakeGameApiClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def health(self) -> dict[str, str]:
        self.calls.append("health")
        return {"status": "ok"}

    def create_game(self, request):
        self.calls.append(f"create:{request.resolved_player_count}")
        return GameResponse(game_id="game-1", state=_state())

    def get_game(self, game_id: str) -> GameResponse:
        self.calls.append(f"get:{game_id}")
        return GameResponse(game_id=game_id, state=_state())

    def list_games(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> GameRunsResponse:
        self.calls.append(f"runs:{status}:{limit}:{offset}")
        run = PublicGameRunSummary(
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
        return GameRunsResponse(runs=[run])

    def step_game(self, game_id: str):
        self.calls.append(f"step:{game_id}")
        return type("Step", (), {"game_id": game_id, "state": _state(), "events": [_event()]})()

    def list_events(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> GameEventsResponse:
        self.calls.append(f"events:{game_id}:{after}:{limit}")
        return GameEventsResponse(game_id=game_id, events=[_event()], next_after=1)

    def list_turns(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> GameTurnsResponse:
        self.calls.append(f"turns:{game_id}:{after}:{limit}")
        turn = PublicGameTurn(
            sequence=1,
            event_sequence=1,
            version=1,
            phase="day_discussion",
            day=1,
            event_type="game_started",
            payload={},
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        return GameTurnsResponse(game_id=game_id, turns=[turn], next_after=1)

    def get_private_observation(
        self,
        game_id: str,
        player_id: str,
        *,
        control_token: str,
    ) -> PrivateObservationResponse:
        self.calls.append(f"observation:{game_id}:{player_id}:{control_token}")
        return PrivateObservationResponse(
            game_id=game_id,
            player_id=player_id,
            observation={"available_actions": ["speech"]},
        )

    def submit_player_action(
        self,
        game_id: str,
        player_id: str,
        request: SubmitPlayerActionRequest,
        *,
        control_token: str,
    ) -> SubmitPlayerActionResponse:
        self.calls.append(f"action:{game_id}:{player_id}:{request.type}:{control_token}")
        return SubmitPlayerActionResponse(
            game_id=game_id,
            player_id=player_id,
            state=_state(),
            events=[_event()],
        )


def test_build_create_game_request_supports_human_player() -> None:
    request = build_create_game_request(
        players=5,
        seed=1,
        human_player="player-2",
        role_count_entries=["werewolf=1", "villager=4"],
        tie_break_policy="no_elimination",
        day_speech_turns=1,
        allow_self_vote=False,
        default_player_count=6,
    )

    assert request.seed == 1
    assert request.resolved_player_count == 5
    assert request.players is not None
    assert request.players[1].agent_type == "human"
    assert request.rule_config.role_counts == {"werewolf": 1, "villager": 4}


def test_build_create_game_request_rejects_unknown_human_player() -> None:
    with pytest.raises(AppError):
        build_create_game_request(
            players=5,
            seed=None,
            human_player="player-9",
            role_count_entries=[],
            tie_break_policy="no_elimination",
            day_speech_turns=1,
            allow_self_vote=False,
            default_player_count=6,
        )


def test_shared_workflows_delegate_to_public_api_client() -> None:
    client = FakeGameApiClient()
    request = build_create_game_request(
        players=2,
        seed=1,
        human_player=None,
        role_count_entries=[],
        tie_break_policy="no_elimination",
        day_speech_turns=1,
        allow_self_vote=False,
        default_player_count=6,
    )

    assert workflows.check_health(client)["status"] == "ok"
    assert workflows.create_game(client, request).game_id == "game-1"
    assert workflows.get_game(client, "game-1").game_id == "game-1"
    assert workflows.list_games(client, limit=10).runs
    assert workflows.list_events(client, "game-1", limit=5).events
    assert workflows.list_turns(client, "game-1", limit=5).turns
    assert workflows.get_private_observation(
        client,
        "game-1",
        "player-1",
        control_token="token",
    ).observation["available_actions"] == ["speech"]
    assert workflows.submit_player_action(
        client,
        "game-1",
        "player-1",
        SubmitPlayerActionRequest(type="speech", message="hello"),
        control_token="token",
    ).events

    assert "health" in client.calls
    assert "action:game-1:player-1:speech:token" in client.calls


def test_http_client_parses_problem_details_from_public_api() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "type": "https://werewolf-agent/errors/resource.not_found",
                "title": "Resource Not Found",
                "status": 404,
                "detail": "Game not found.",
                "instance": "/api/v1/games/missing",
                "code": "resource.not_found",
            },
        )

    client = HttpGameApiClient(
        "http://api.test/api/v1",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AppError) as exc_info:
        client.get_game("missing")

    assert exc_info.value.detail == "resource.not_found: Game not found."
    assert exc_info.value.context["http_status"] == 404


def test_http_client_propagates_trace_id_header() -> None:
    seen_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers["x-trace-id"] = request.headers["x-trace-id"]
        return httpx.Response(200, json={"status": "ok", "service": "api"})

    client = HttpGameApiClient(
        "http://api.test/api/v1",
        transport=httpx.MockTransport(handler),
    )

    with bind_observation_context(trace_id="trace-client"):
        client.health()

    assert seen_headers["x-trace-id"] == "trace-client"


def test_diagnostics_redacts_database_password() -> None:
    settings = AppSettings(
        _env_file=None,
        database_url="postgres://user:secret@example.test:5432/werewolf_agent",
    )

    diagnostics = build_interface_diagnostics(
        settings=settings,
        api_url="http://api.test/api/v1",
        api_health="ok",
    )

    assert diagnostics["api url"] == "http://api.test/api/v1"
    assert "secret" not in diagnostics["database"]
    assert "[REDACTED]" in diagnostics["database"]
