import httpx
import pytest

from werewolf_agent.contracts import AppError
from werewolf_agent.interface.entrypoint.shared import (
    HttpGameApiClient,
    build_create_game_request,
)


def test_build_create_game_request_marks_one_human_player() -> None:
    request = build_create_game_request(
        players=5,
        seed=1,
        human_player="player-2",
        role_count=["werewolf=1", "villager=4"],
        tie_break_policy="no_elimination",
        day_speech_turns=1,
        allow_self_vote=False,
        default_player_count=6,
    )

    assert request.player_count is None
    assert request.resolved_player_count == 5
    assert request.players is not None
    assert [player.agent_type for player in request.players] == [
        "llm",
        "human",
        "llm",
        "llm",
        "llm",
    ]
    assert request.rule_config.role_counts == {"werewolf": 1, "villager": 4}


def test_build_create_game_request_rejects_unknown_human_player() -> None:
    with pytest.raises(AppError):
        build_create_game_request(
            players=5,
            seed=1,
            human_player="player-9",
            role_count=[],
            tie_break_policy="no_elimination",
            day_speech_turns=1,
            allow_self_vote=False,
            default_player_count=6,
        )


def test_http_client_keeps_public_v1_contract() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        return httpx.Response(200, json={"status": "ok", "service": "werewolf-agent-api"})

    client = HttpGameApiClient(
        "http://api.test/api/v1",
        transport=httpx.MockTransport(handler),
    )

    assert client.health()["status"] == "ok"
    assert requests == [("GET", "/api/v1/health")]
