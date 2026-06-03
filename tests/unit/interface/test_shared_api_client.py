from datetime import UTC, datetime

import httpx
import pytest

from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.schemas import PlayerActionRequest
from werewolf_agent.interface.runtime import AppSettings, bind_observation_context
from werewolf_agent.interface.shared.api_client import HttpGameApiClient
from werewolf_agent.interface.shared.diagnostics import build_interface_diagnostics
from werewolf_agent.interface.shared.game_requests import build_create_game_request

HTTP_CLIENT_TEST_TIMEOUT = 1.0


def test_build_create_game_request_supports_manual_player() -> None:
    request = build_create_game_request(
        seed=1,
        manual_player_id="player-2",
        role_counts={"werewolf": 1, "villager": 4},
    )

    assert request.seed == 1
    assert request.player_count == 5
    assert request.manual_player_id == "player-2"
    assert request.role_counts == {"werewolf": 1, "villager": 4}
    assert request.narration_mode is None
    assert request.rules is None


def test_build_create_game_request_rejects_unknown_manual_player() -> None:
    with pytest.raises(AppError):
        build_create_game_request(
            seed=None,
            manual_player_id="player-9",
            role_counts={"werewolf": 1, "villager": 4},
        )


def test_http_client_uses_minimal_public_v1_contract() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json={"status": "ok", "service": "api"})
        if request.url.path.endswith("/setup-options"):
            return httpx.Response(200, json=_setup_options_payload())
        if request.url.path.endswith("/games") and request.method == "POST":
            return httpx.Response(201, json=_game_payload())
        if request.url.path.endswith("/games") and request.method == "GET":
            return httpx.Response(200, json={"games": [_run_payload()]})
        if request.url.path.endswith("/games/game-1"):
            return httpx.Response(200, json=_game_payload())
        if request.url.path.endswith("/games/game-1/reveal"):
            return httpx.Response(200, json=_reveal_payload())
        if request.url.path.endswith("/games/game-1/advance"):
            return httpx.Response(
                200, json={**_game_payload(), "status": "running", "timeline": []}
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
        timeout=HTTP_CLIENT_TEST_TIMEOUT,
        transport=httpx.MockTransport(handler),
    )
    request = build_create_game_request(
        seed=1,
        manual_player_id=None,
        role_counts={"werewolf": 1, "villager": 4},
    )

    assert client.health()["status"] == "ok"
    assert client.get_setup_options().default_role_counts == {"werewolf": 1, "villager": 4}
    assert client.create_game(request).game_id == "game-1"
    assert client.list_games().games
    assert client.get_game("game-1").game_id == "game-1"
    assert client.get_game_reveal("game-1").players[1].role == "werewolf"
    assert client.advance_game("game-1").game_id == "game-1"
    assert client.get_timeline("game-1").items
    assert (
        client.get_private_observation(
            "game-1",
            "player-1",
            manual_token="token",
        ).player_id
        == "player-1"
    )
    assert (
        client.submit_player_action(
            "game-1",
            "player-1",
            PlayerActionRequest(type="speech", message="hello"),
            manual_token="token",
        ).timeline
        == []
    )

    assert requests == [
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/setup-options"),
        ("POST", "/api/v1/games"),
        ("GET", "/api/v1/games"),
        ("GET", "/api/v1/games/game-1"),
        ("GET", "/api/v1/games/game-1/reveal"),
        ("POST", "/api/v1/games/game-1/advance"),
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
        timeout=HTTP_CLIENT_TEST_TIMEOUT,
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
        timeout=HTTP_CLIENT_TEST_TIMEOUT,
        transport=httpx.MockTransport(handler),
    )

    with bind_observation_context(trace_id="trace-client"):
        client.health()

    assert seen_headers["x-trace-id"] == "trace-client"


def test_diagnostics_redacts_database_password() -> None:
    settings = AppSettings(
        _env_file=None,
        database_url="postgres://user:secret@example.test:5432/werewolf_agent",
        openai_api_key="sk-secret",
    )

    diagnostics = build_interface_diagnostics(
        settings=settings,
        api_url="http://api.test/api/v1",
        api_health="ok",
    )

    assert diagnostics["api url"] == "http://api.test/api/v1"
    assert "secret" not in diagnostics["database"]
    assert "[REDACTED]" in diagnostics["database"]
    assert diagnostics["llm api key"] == "[REDACTED]"
    assert "sk-secret" not in str(diagnostics)


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


def _reveal_payload() -> dict[str, object]:
    return {
        "game_id": "game-1",
        "status": "running",
        "phase": "day_discussion",
        "day": 1,
        "version": 1,
        "seed": 1,
        "role_counts": {"werewolf": 1, "villager": 1},
        "rules": _setup_options_payload()["default_rules"],
        "players": [
            {
                "id": "player-1",
                "name": "Player 1",
                "role": "villager",
                "faction": "village",
                "alive": True,
                "status": "alive",
            },
            {
                "id": "player-2",
                "name": "Player 2",
                "role": "werewolf",
                "faction": "werewolf",
                "alive": True,
                "status": "alive",
            },
        ],
        "alive_player_ids": ["player-1", "player-2"],
        "eliminated_player_ids": [],
    }


def _setup_options_payload() -> dict[str, object]:
    return {
        "player_count": {"min": 5, "max": 8},
        "roles": [
            {"id": "villager", "name": "Villager", "faction": "village", "abilities": []},
            {"id": "werewolf", "name": "Werewolf", "faction": "werewolf", "abilities": []},
        ],
        "default_role_counts": {"werewolf": 1, "villager": 4},
        "default_rules": {
            "day_speech_limit_per_player": 1,
            "allow_self_vote": False,
            "allow_vote_revision": False,
            "allow_night_action_revision": False,
            "enable_first_night_attack": False,
            "enable_no_elimination_on_tie": True,
            "enable_random_elimination_on_tie": False,
            "allow_knight_self_guard": True,
            "allow_knight_repeat_guard": True,
            "allow_seer_self_inspect": False,
            "allow_werewolf_friendly_fire": False,
            "reveal_role_on_death": False,
        },
    }
