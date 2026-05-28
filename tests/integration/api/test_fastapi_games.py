import json
from collections.abc import Iterator
from uuid import uuid4

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from werewolf_agent.interface.api.app import create_app  # noqa: E402
from werewolf_agent.interface.shared.settings import AppSettings  # noqa: E402


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    settings = AppSettings(
        _env_file=None,
        api_debug=False,
        database_url="sqlite+pysqlite:///:memory:",
    )
    app = create_app(settings, create_schema=True)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.state.engine.dispose()


def _create_payload() -> dict[str, object]:
    return {
        "seed": 42,
        "players": [
            {"id": "p1", "name": "Alice", "agent_type": "llm"},
            {"id": "p2", "name": "Bob", "agent_type": "llm"},
            {"id": "p3", "name": "Carol", "agent_type": "llm"},
            {"id": "p4", "name": "Dave", "agent_type": "llm"},
            {"id": "p5", "name": "Eve", "agent_type": "llm"},
        ],
    }


def test_health_endpoint_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Trace-Id": "trace-test"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "werewolf-agent-api"}
    assert response.headers["x-trace-id"] == "trace-test"


def test_default_ruleset_endpoint_returns_mvp_metadata(client: TestClient) -> None:
    response = client.get("/api/v1/rulesets/default")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "default"
    assert payload["player_count"] == {"min": 5, "max": 8}
    assert {role["id"] for role in payload["roles"]} == {
        "villager",
        "werewolf",
        "seer",
        "knight",
    }
    assert payload["agent_types"] == [
        {"id": "llm", "name": "LLM Agent"},
        {"id": "human", "name": "Human Player"},
    ]


def test_create_game_returns_public_state_without_private_fields(client: TestClient) -> None:
    response = client.post("/api/v1/games", json=_create_payload())

    assert response.status_code == 201
    payload = response.json()
    state = payload["state"]
    serialized = json.dumps(payload)

    assert payload["game_id"]
    assert state["game_id"] == payload["game_id"]
    assert state["status"] == "running"
    assert state["phase"] == "night"
    assert state["day"] == 1
    assert state["version"] == 1
    assert state["seed"] == 42
    assert [player["id"] for player in state["players"]] == ["p1", "p2", "p3", "p4", "p5"]
    assert "private_state" not in serialized
    assert "role" not in serialized
    assert "werewolf" not in serialized


def test_human_player_create_returns_control_token_once(client: TestClient) -> None:
    payload = _create_payload()
    payload["players"][0]["agent_type"] = "human"

    response = client.post("/api/v1/games", json=payload)

    assert response.status_code == 201
    created = response.json()
    game_id = created["game_id"]
    assert set(created["control_tokens"]) == {"p1"}
    assert created["control_tokens"]["p1"]

    state_response = client.get(f"/api/v1/games/{game_id}")
    events_response = client.get(f"/api/v1/games/{game_id}/events?after=0")

    assert "control_tokens" not in state_response.json()
    serialized_public = json.dumps([state_response.json(), events_response.json()])
    assert created["control_tokens"]["p1"] not in serialized_public
    assert "control_token" not in serialized_public


def test_private_observation_requires_valid_control_token(client: TestClient) -> None:
    payload = _create_payload()
    payload["players"][0]["agent_type"] = "human"
    created = client.post("/api/v1/games", json=payload).json()
    game_id = created["game_id"]
    token = created["control_tokens"]["p1"]
    url = f"/api/v1/games/{game_id}/players/p1/observation"

    missing = client.get(url)
    invalid = client.get(url, headers={"Authorization": "Bearer wrong"})
    valid = client.get(url, headers={"Authorization": f"Bearer {token}"})

    assert missing.status_code == 401
    assert missing.json()["code"] == "auth.required"
    assert invalid.status_code == 403
    assert invalid.json()["code"] == "auth.forbidden"
    assert valid.status_code == 200
    assert valid.json()["player_id"] == "p1"
    assert valid.json()["observation"]["me"]["role"]


def test_private_player_endpoints_reject_non_human_player(client: TestClient) -> None:
    payload = _create_payload()
    payload["players"][0]["agent_type"] = "human"
    created = client.post("/api/v1/games", json=payload).json()
    game_id = created["game_id"]
    token = created["control_tokens"]["p1"]
    headers = {"Authorization": f"Bearer {token}"}

    observation = client.get(
        f"/api/v1/games/{game_id}/players/p2/observation",
        headers=headers,
    )
    action = client.post(
        f"/api/v1/games/{game_id}/players/p2/actions",
        json={"type": "pass"},
        headers=headers,
    )

    assert observation.status_code == 403
    assert observation.json()["code"] == "auth.forbidden"
    assert action.status_code == 403
    assert action.json()["code"] == "auth.forbidden"


def test_human_player_can_submit_manual_action(client: TestClient) -> None:
    payload = _create_payload()
    payload["players"][0]["agent_type"] = "human"
    created = client.post("/api/v1/games", json=payload).json()
    game_id = created["game_id"]
    token = created["control_tokens"]["p1"]
    headers = {"Authorization": f"Bearer {token}"}

    observation = {}
    for _ in range(8):
        client.post(f"/api/v1/games/{game_id}/steps")
        observation = client.get(
            f"/api/v1/games/{game_id}/players/p1/observation",
            headers=headers,
        ).json()["observation"]
        if observation["available_actions"]:
            break

    assert observation["available_actions"]
    action_type = observation["available_actions"][0]
    action_payload = {"type": action_type}
    if action_type == "speech":
        action_payload["message"] = "I am checking the table."
    elif action_type != "pass":
        target = next(player["id"] for player in observation["players"] if player["id"] != "p1")
        action_payload["target_id"] = target

    response = client.post(
        f"/api/v1/games/{game_id}/players/p1/actions",
        json=action_payload,
        headers=headers,
    )

    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert token not in serialized
    assert "control_token" not in serialized


def test_steps_complete_game_and_events_are_public_only(client: TestClient) -> None:
    create_response = client.post("/api/v1/games", json={"player_count": 6, "seed": 1})
    game_id = create_response.json()["game_id"]

    state = create_response.json()["state"]
    event_payload = {"events": []}
    for _ in range(32):
        step_response = client.post(f"/api/v1/games/{game_id}/steps")
        assert step_response.status_code == 200
        step_payload = step_response.json()
        state = step_payload["state"]
        event_payload = client.get(f"/api/v1/games/{game_id}/events?after=0").json()
        if state["status"] == "completed":
            break

    assert state["status"] == "completed"
    assert state["winner"] in {"villagers", "werewolves"}
    assert event_payload["events"]
    assert all(event["visibility"] == "public" for event in event_payload["events"])
    assert "role" not in json.dumps(event_payload)
    assert "private_state" not in json.dumps(event_payload)


def test_game_list_and_turns_return_public_read_models(client: TestClient) -> None:
    created = client.post("/api/v1/games", json={"player_count": 5, "seed": 2}).json()
    game_id = created["game_id"]
    client.post(f"/api/v1/games/{game_id}/steps")

    runs_response = client.get("/api/v1/games?limit=10")
    turns_response = client.get(f"/api/v1/games/{game_id}/turns?after=0")

    assert runs_response.status_code == 200
    assert turns_response.status_code == 200
    runs_payload = runs_response.json()
    turns_payload = turns_response.json()
    assert any(run["game_id"] == game_id for run in runs_payload["runs"])
    assert turns_payload["turns"]
    assert "role_counts" not in json.dumps(turns_payload)


def test_public_event_stream_returns_sse_batch(client: TestClient) -> None:
    created = client.post("/api/v1/games", json={"player_count": 5, "seed": 2}).json()

    response = client.get(f"/api/v1/games/{created['game_id']}/events/stream?after=0")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: game_event" in response.text
    assert "data:" in response.text


def test_finished_game_step_returns_problem_details(client: TestClient) -> None:
    created = client.post("/api/v1/games", json={"player_count": 6, "seed": 1}).json()
    step_url = f"/api/v1/games/{created['game_id']}/steps"
    state = created["state"]
    for _ in range(32):
        response = client.post(step_url)
        state = response.json()["state"]
        if state["status"] == "completed":
            break

    response = client.post(step_url)

    assert state["status"] == "completed"
    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "game.invalid_phase"


def test_create_game_rejects_unsupported_agent_type_as_game_action_error(
    client: TestClient,
) -> None:
    payload = _create_payload()
    payload["players"][0]["agent_type"] = "dummy"

    response = client.post("/api/v1/games", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "game.invalid_action"


def test_create_game_rejects_unsupported_top_level_agent_type(client: TestClient) -> None:
    response = client.post("/api/v1/games", json={"player_count": 5, "agent": {"type": "dummy"}})

    assert response.status_code == 422
    assert response.json()["code"] == "game.invalid_action"


def test_create_game_rejects_invalid_rule_config_as_validation_error(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/games",
        json={
            "player_count": 5,
            "rule_config": {"tie_break_policy": "coin_flip"},
        },
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "request.validation_failed"
    assert response.json()["errors"][0]["pointer"] == "/rule_config/tie_break_policy"


def test_day_speech_turns_controls_api_discussion_actions(client: TestClient) -> None:
    created = client.post(
        "/api/v1/games",
        json={
            "player_count": 5,
            "seed": 3,
            "rule_config": {"day_speech_turns": 2},
        },
    ).json()
    game_id = created["game_id"]

    after_night = client.post(f"/api/v1/games/{game_id}/steps").json()["state"]
    response = client.post(f"/api/v1/games/{game_id}/steps")

    assert response.status_code == 200
    speech_events = [
        event for event in response.json()["events"] if event["event_type"] == "speech_recorded"
    ]
    assert len(speech_events) == len(after_night["alive_player_ids"]) * 2


def test_create_game_validation_errors_use_problem_details(client: TestClient) -> None:
    response = client.post(
        "/api/v1/games",
        json={"players": [{"id": "p1", "agent_type": "llm"}]},
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "request.validation_failed"
    assert response.json()["errors"][0]["pointer"] == "/players/0/name"


def test_missing_game_returns_problem_details(client: TestClient) -> None:
    response = client.get(f"/api/v1/games/{uuid4()}")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "resource.not_found"
    assert response.headers["x-trace-id"]
    assert response.json()["trace_id"] == response.headers["x-trace-id"]


def test_invalid_game_id_is_handled_by_usecase_boundary(client: TestClient) -> None:
    response = client.get("/api/v1/games/not-a-uuid")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "resource.not_found"


def test_method_not_allowed_returns_problem_details(client: TestClient) -> None:
    response = client.post("/api/v1/health")

    assert response.status_code == 405
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "request.method_not_allowed"
    assert response.json()["type"] == "tag:werewolf-agent,2026:problem:request.method_not_allowed"


def test_missing_api_route_returns_problem_details(client: TestClient) -> None:
    response = client.get("/api/v1/missing")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "resource.not_found"
    assert response.json()["instance"] == "/api/v1/missing"
