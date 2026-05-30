from datetime import UTC, datetime

import httpx
import pytest

from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.schemas import PlayerActionRequest
from werewolf_agent.interface.runtime import AppSettings, bind_observation_context
from werewolf_agent.interface.shared.api_client import HttpGameApiClient
from werewolf_agent.interface.shared.diagnostics import build_interface_diagnostics
from werewolf_agent.interface.shared.game_requests import build_create_game_request


def test_build_create_game_request_supports_human_player() -> None:
    request = build_create_game_request(
        players=5,
        seed=1,
        human_player="player-2",
        role_count_entries=["werewolf=1", "villager=4"],
        tie_break_policy="no_elimination",
        day_speech_turns=1,
        allow_self_vote=False,
        allow_action_revisions=False,
        default_player_count=6,
    )

    assert request.seed == 1
    assert request.player_count is None
    assert request.players is not None
    assert len(request.players) == 5
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
            allow_action_revisions=False,
            default_player_count=6,
        )


def test_http_client_uses_minimal_public_v1_contract() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json={"status": "ok", "service": "api"})
        if request.url.path.endswith("/ruleset"):
            return httpx.Response(200, json=_ruleset_payload())
        if request.url.path.endswith("/games") and request.method == "POST":
            return httpx.Response(201, json=_game_payload())
        if request.url.path.endswith("/games") and request.method == "GET":
            return httpx.Response(200, json={"runs": [_run_payload()]})
        if request.url.path.endswith("/games/game-1"):
            return httpx.Response(200, json=_game_payload())
        if request.url.path.endswith("/games/game-1/advance"):
            return httpx.Response(
                200, json={**_game_payload(), "status": "running", "timeline": []}
            )
        if request.url.path.endswith("/games/game-1/advance-until-input"):
            return httpx.Response(
                200,
                json={
                    **_game_payload(),
                    "status": "running",
                    "timeline": [],
                    "stop_reason": "manual_input_required",
                    "steps": 1,
                },
            )
        if request.url.path.endswith("/games/game-1/timeline"):
            return httpx.Response(
                200, json={"game_id": "game-1", "items": [_timeline_item()], "next_after": 1}
            )
        if request.url.path.endswith("/games/game-1/players/player-1/observation"):
            return httpx.Response(
                200, json={"game_id": "game-1", "player_id": "player-1", "observation": {}}
            )
        if request.url.path.endswith("/games/game-1/players/player-1/actions"):
            return httpx.Response(
                200, json={**_game_payload(), "player_id": "player-1", "timeline": []}
            )
        return httpx.Response(404, json={})

    client = HttpGameApiClient(
        "http://api.test/api/v1",
        transport=httpx.MockTransport(handler),
    )
    request = build_create_game_request(
        players=5,
        seed=1,
        human_player=None,
        role_count_entries=[],
        tie_break_policy="no_elimination",
        day_speech_turns=1,
        allow_self_vote=False,
        allow_action_revisions=False,
        default_player_count=6,
    )

    assert client.health()["status"] == "ok"
    assert client.get_ruleset().id == "default"
    assert client.create_game(request).game_id == "game-1"
    assert client.list_games().runs
    assert client.get_game("game-1").game_id == "game-1"
    assert client.advance_game("game-1").game_id == "game-1"
    assert client.advance_until_input("game-1", max_steps=3).stop_reason == "manual_input_required"
    assert client.get_timeline("game-1").items
    assert (
        client.get_private_observation(
            "game-1",
            "player-1",
            control_token="token",
        ).player_id
        == "player-1"
    )
    assert (
        client.submit_player_action(
            "game-1",
            "player-1",
            PlayerActionRequest(type="speech", message="hello"),
            control_token="token",
        ).timeline
        == []
    )

    assert requests == [
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/ruleset"),
        ("POST", "/api/v1/games"),
        ("GET", "/api/v1/games"),
        ("GET", "/api/v1/games/game-1"),
        ("POST", "/api/v1/games/game-1/advance"),
        ("POST", "/api/v1/games/game-1/advance-until-input"),
        ("GET", "/api/v1/games/game-1/timeline"),
        ("GET", "/api/v1/games/game-1/players/player-1/observation"),
        ("POST", "/api/v1/games/game-1/players/player-1/actions"),
    ]


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


def _game_payload() -> dict[str, object]:
    return {"game_id": "game-1", "state": _state_payload()}


def _state_payload() -> dict[str, object]:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    return {
        "game_id": "game-1",
        "status": "running",
        "phase": "day_discussion",
        "day": 1,
        "version": 1,
        "seed": 1,
        "players": [
            {"id": "player-1", "name": "Player 1", "alive": True, "status": "alive"},
            {"id": "player-2", "name": "Player 2", "alive": True, "status": "alive"},
        ],
        "alive_player_ids": ["player-1", "player-2"],
        "eliminated_player_ids": [],
        "summary": {"alive_count": 2},
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _run_payload() -> dict[str, object]:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    return {
        "game_id": "game-1",
        "status": "running",
        "phase": "day_discussion",
        "day": 1,
        "version": 1,
        "seed": 1,
        "player_count": 2,
        "alive_count": 2,
        "step_count": 0,
        "turn_count": 1,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _timeline_item() -> dict[str, object]:
    return {
        "sequence": 1,
        "event_sequence": 1,
        "version": 1,
        "phase": "day_discussion",
        "day": 1,
        "event_type": "game_started",
        "payload": {"player_count": 2},
        "occurred_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
    }


def _ruleset_payload() -> dict[str, object]:
    return {
        "id": "default",
        "name": "MVP Default",
        "description": "default rules",
        "player_count": {"min": 5, "max": 8},
        "roles": [{"id": "villager", "name": "Villager"}],
        "phases": [{"id": "night", "name": "Night"}],
        "agent_types": [{"id": "llm", "name": "LLM Agent"}],
    }
