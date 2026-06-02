import json
import logging
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from werewolf_agent.interface.api.app import create_app  # noqa: E402
from werewolf_agent.interface.runtime import AppSettings  # noqa: E402

DEFAULT_ROLE_COUNTS = {"werewolf": 1, "seer": 1, "knight": 1, "villager": 2}
SIX_PLAYER_ROLE_COUNTS = {"werewolf": 1, "seer": 1, "knight": 1, "villager": 3}


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    settings = AppSettings(
        _env_file=None,
        api_debug=False,
        database_url="sqlite+pysqlite:///:memory:",
        log_output="none",
    )
    app = create_app(settings, create_schema=True)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.state.engine.dispose()


def _create_payload(
    *,
    human_player_id: str | None = None,
    role_counts: dict[str, int] | None = None,
    seed: int | None = 42,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "seed": seed,
        "role_counts": role_counts or DEFAULT_ROLE_COUNTS,
    }
    if human_player_id is not None:
        payload["human_player_id"] = human_player_id
    return payload


def _manual_action_payload(observation: dict[str, object], *, player_id: str) -> dict[str, object]:
    action_type = str(observation["available_actions"][0])
    payload: dict[str, object] = {"type": action_type}
    if action_type == "speech":
        payload["message"] = "I am checking the table."
        return payload
    known_roles = observation.get("known_roles")
    known_wolves = set()
    if isinstance(known_roles, dict):
        known_wolves = {
            str(target_id) for target_id, role in known_roles.items() if role == "werewolf"
        }
    players = observation.get("players")
    assert isinstance(players, list)
    target = next(
        str(player["id"])
        for player in players
        if isinstance(player, dict)
        and player.get("id") != player_id
        and player.get("status") == "alive"
        and player.get("id") not in known_wolves
    )
    payload["target_id"] = target
    return payload


def test_health_endpoint_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Trace-Id": "trace-test"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "werewolf-agent-api"}
    assert response.headers["x-trace-id"] == "trace-test"


def test_request_logging_writes_trace_and_http_fields(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        api_debug=False,
        sqlite_path=tmp_path / "api.sqlite3",
        log_output="file",
        log_dir=tmp_path,
        log_file_name="api.jsonl",
    )
    app = create_app(settings, create_schema=True)
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = test_client.get("/api/v1/health", headers={"X-Trace-Id": "trace-log"})
    finally:
        app.state.engine.dispose()

    for handler in logging.getLogger().handlers:
        handler.flush()
    payloads = [
        json.loads(line)
        for line in settings.log_file_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    startup_payload = next(
        payload for payload in payloads if payload["event.action"] == "api.application.started"
    )
    request_payload = next(
        payload for payload in payloads if payload["event.action"] == "http.request.completed"
    )

    assert response.status_code == 200
    assert startup_payload["event.outcome"] == "success"
    assert startup_payload["database_backend"] == "sqlite"
    assert startup_payload["database_source"] == "sqlite_path"
    assert startup_payload["sqlite_path"] == str(settings.sqlite_database_path)
    assert startup_payload["log_output"] == "file"
    assert startup_payload["log_file_path"] == str(settings.log_file_path)
    assert "database_url" not in startup_payload
    assert request_payload["message"] == "http.request.completed"
    assert request_payload["event.outcome"] == "success"
    assert request_payload["trace.id"] == "trace-log"
    assert request_payload["http.request.method"] == "GET"
    assert request_payload["url.path"] == "/api/v1/health"
    assert request_payload["http.response.status_code"] == 200
    assert isinstance(request_payload["event.duration"], int)


def test_application_logs_share_request_trace_id(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        api_debug=False,
        database_url="sqlite+pysqlite:///:memory:",
        log_output="file",
        log_dir=tmp_path,
        log_file_name="api.jsonl",
    )
    app = create_app(settings, create_schema=True)
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = test_client.post(
                "/api/v1/games",
                json=_create_payload(seed=1),
                headers={"X-Trace-Id": "trace-create"},
            )
    finally:
        app.state.engine.dispose()

    for handler in logging.getLogger().handlers:
        handler.flush()
    payloads = [
        json.loads(line)
        for line in settings.log_file_path.read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert response.status_code == 201
    game_log = next(
        payload for payload in payloads if payload["event.action"] == "game.run.created"
    )
    request_log = next(
        payload for payload in payloads if payload["event.action"] == "http.request.completed"
    )
    assert game_log["trace.id"] == "trace-create"
    assert request_log["trace.id"] == "trace-create"


def test_api_logs_expected_user_error_at_info(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        api_debug=False,
        database_url="sqlite+pysqlite:///:memory:",
        log_output="file",
        log_dir=tmp_path,
        log_file_name="api.jsonl",
    )
    app = create_app(settings, create_schema=True)
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = test_client.post(
                "/api/v1/games",
                json={"role_counts": {"werewolf": 1, "villager": 3}},
                headers={"X-Trace-Id": "trace-invalid-action"},
            )
    finally:
        app.state.engine.dispose()

    for handler in logging.getLogger().handlers:
        handler.flush()
    payloads = [
        json.loads(line)
        for line in settings.log_file_path.read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert response.status_code == 422
    error_log = next(
        payload
        for payload in payloads
        if payload["event.action"] == "http.application_error.handled"
    )
    assert error_log["log.level"] == "INFO"
    assert error_log["event.outcome"] == "failure"
    assert error_log["trace.id"] == "trace-invalid-action"
    assert error_log["error.code"] == "game.invalid_action"


def test_default_ruleset_endpoint_returns_mvp_metadata(client: TestClient) -> None:
    response = client.get("/api/v1/ruleset")

    assert response.status_code == 200
    payload = response.json()
    assert payload["player_count"] == {"min": 5, "max": 8}
    assert {role["id"] for role in payload["roles"]} == {
        "villager",
        "werewolf",
        "seer",
        "knight",
    }
    assert payload["default_role_counts"] == {
        "werewolf": 1,
        "seer": 1,
        "knight": 1,
        "villager": 3,
    }
    assert payload["default_rules"]["enable_no_elimination_on_tie"] is True
    assert payload["default_scenario_id"] == "classic_village"
    assert payload["default_setup_preset_id"] == "standard_6"
    assert {scenario["id"] for scenario in payload["scenarios"]} >= {
        "classic_village",
        "sealed_lab",
    }
    assert {character["name"] for character in payload["characters"]} >= {"葵", "蓮"}


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
    assert state["scenario_id"] == "classic_village"
    assert state["scenario_name"] == "古い村"
    assert [player["id"] for player in state["players"]] == [
        "player-1",
        "player-2",
        "player-3",
        "player-4",
        "player-5",
    ]
    assert "private_state" not in serialized
    assert "role" not in serialized
    assert "werewolf" not in serialized


def test_human_player_create_returns_control_token_once(client: TestClient) -> None:
    payload = _create_payload(human_player_id="player-1")

    response = client.post("/api/v1/games", json=payload)

    assert response.status_code == 201
    created = response.json()
    game_id = created["game_id"]
    assert set(created["control_tokens"]) == {"player-1"}
    assert created["control_tokens"]["player-1"]

    state_response = client.get(f"/api/v1/games/{game_id}")
    timeline_response = client.get(f"/api/v1/games/{game_id}/timeline?after=0")

    assert "control_tokens" not in state_response.json()
    serialized_public = json.dumps([state_response.json(), timeline_response.json()])
    assert created["control_tokens"]["player-1"] not in serialized_public
    assert "control_token" not in serialized_public


def test_reveal_endpoint_returns_dedicated_private_dto(client: TestClient) -> None:
    created = client.post("/api/v1/games", json=_create_payload(seed=1)).json()
    game_id = created["game_id"]
    client.post(f"/api/v1/games/{game_id}/advance")

    reveal_response = client.get(f"/api/v1/games/{game_id}/reveal")
    public_response = client.get(f"/api/v1/games/{game_id}")
    timeline_response = client.get(f"/api/v1/games/{game_id}/timeline?after=0")

    assert reveal_response.status_code == 200
    reveal = reveal_response.json()
    assert reveal["role_counts"] == DEFAULT_ROLE_COUNTS
    assert {player["role"] for player in reveal["players"]} >= {"werewolf", "villager"}
    assert reveal["nights"]
    assert "role" not in json.dumps(public_response.json())
    assert "attacked_player_id" not in json.dumps(timeline_response.json())


def test_reveal_endpoint_can_be_disabled() -> None:
    settings = AppSettings(
        _env_file=None,
        api_debug=False,
        database_url="sqlite+pysqlite:///:memory:",
        log_output="none",
        reveal_api_enabled=False,
    )
    app = create_app(settings, create_schema=True)
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            created = test_client.post("/api/v1/games", json=_create_payload()).json()
            response = test_client.get(f"/api/v1/games/{created['game_id']}/reveal")
    finally:
        app.state.engine.dispose()

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "auth.forbidden"


def test_private_observation_requires_valid_control_token(client: TestClient) -> None:
    payload = _create_payload(human_player_id="player-1")
    created = client.post("/api/v1/games", json=payload).json()
    game_id = created["game_id"]
    token = created["control_tokens"]["player-1"]
    url = f"/api/v1/games/{game_id}/players/player-1/observation"

    missing = client.get(url)
    invalid = client.get(url, headers={"Authorization": "Bearer wrong"})
    valid = client.get(url, headers={"Authorization": f"Bearer {token}"})

    assert missing.status_code == 401
    assert missing.json()["code"] == "auth.required"
    assert invalid.status_code == 403
    assert invalid.json()["code"] == "auth.forbidden"
    assert valid.status_code == 200
    assert valid.json()["player_id"] == "player-1"
    assert valid.json()["observation"]["me"]["role"]


def test_private_player_endpoints_reject_non_human_player(client: TestClient) -> None:
    payload = _create_payload(human_player_id="player-1")
    created = client.post("/api/v1/games", json=payload).json()
    game_id = created["game_id"]
    token = created["control_tokens"]["player-1"]
    headers = {"Authorization": f"Bearer {token}"}

    observation = client.get(
        f"/api/v1/games/{game_id}/players/player-2/observation",
        headers=headers,
    )
    action = client.post(
        f"/api/v1/games/{game_id}/players/player-2/actions",
        json={"type": "pass"},
        headers=headers,
    )

    assert observation.status_code == 403
    assert observation.json()["code"] == "auth.forbidden"
    assert action.status_code == 403
    assert action.json()["code"] == "auth.forbidden"


def test_human_player_can_submit_manual_action(client: TestClient) -> None:
    payload = _create_payload(human_player_id="player-1")
    created = client.post("/api/v1/games", json=payload).json()
    game_id = created["game_id"]
    token = created["control_tokens"]["player-1"]
    headers = {"Authorization": f"Bearer {token}"}

    stopped = client.post(f"/api/v1/games/{game_id}/advance-until-input?max_steps=8")
    observation = client.get(
        f"/api/v1/games/{game_id}/players/player-1/observation",
        headers=headers,
    ).json()["observation"]

    assert stopped.status_code == 200
    assert stopped.json()["stop_reason"] == "manual_input_required"
    assert observation["available_actions"]
    action_payload = _manual_action_payload(observation, player_id="player-1")

    response = client.post(
        f"/api/v1/games/{game_id}/players/player-1/actions",
        json=action_payload,
        headers=headers,
    )
    duplicate = client.post(
        f"/api/v1/games/{game_id}/players/player-1/actions",
        json=action_payload,
        headers=headers,
    )

    assert response.status_code == 200
    assert duplicate.status_code == 422
    assert duplicate.json()["code"] == "game.invalid_action"
    serialized = json.dumps(response.json())
    assert token not in serialized
    assert "control_token" not in serialized


def test_advance_completes_game_and_timeline_is_public_only(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/games",
        json=_create_payload(role_counts=SIX_PLAYER_ROLE_COUNTS, seed=1),
    )
    game_id = create_response.json()["game_id"]

    state = create_response.json()["state"]
    timeline_payload = {"items": []}
    for _ in range(32):
        advance_response = client.post(f"/api/v1/games/{game_id}/advance")
        assert advance_response.status_code == 200
        advance_payload = advance_response.json()
        state = advance_payload["state"]
        timeline_payload = client.get(f"/api/v1/games/{game_id}/timeline?after=0").json()
        if state["status"] == "completed":
            break

    assert state["status"] == "completed"
    assert state["winner"] in {"villagers", "werewolves"}
    assert timeline_payload["items"]
    assert "role" not in json.dumps(timeline_payload)
    assert "private_state" not in json.dumps(timeline_payload)


def test_game_list_and_timeline_return_public_read_models(client: TestClient) -> None:
    created = client.post("/api/v1/games", json=_create_payload(seed=2)).json()
    game_id = created["game_id"]
    client.post(f"/api/v1/games/{game_id}/advance")

    runs_response = client.get("/api/v1/games?limit=10")
    timeline_response = client.get(f"/api/v1/games/{game_id}/timeline?after=0")

    assert runs_response.status_code == 200
    assert timeline_response.status_code == 200
    runs_payload = runs_response.json()
    timeline_payload = timeline_response.json()
    assert any(run["game_id"] == game_id for run in runs_payload["runs"])
    assert not any(player["name"].startswith("Player ") for player in created["state"]["players"])
    assert timeline_payload["items"]
    assert "role_counts" not in json.dumps(timeline_payload)


def test_public_timeline_stream_returns_sse_batch(client: TestClient) -> None:
    created = client.post("/api/v1/games", json=_create_payload(seed=2)).json()

    response = client.get(f"/api/v1/games/{created['game_id']}/timeline/stream?after=0")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: timeline_item" in response.text
    assert "data:" in response.text


def test_finished_game_advance_returns_problem_details(client: TestClient) -> None:
    created = client.post(
        "/api/v1/games",
        json=_create_payload(role_counts=SIX_PLAYER_ROLE_COUNTS, seed=1),
    ).json()
    advance_url = f"/api/v1/games/{created['game_id']}/advance"
    state = created["state"]
    for _ in range(32):
        response = client.post(advance_url)
        state = response.json()["state"]
        if state["status"] == "completed":
            break

    response = client.post(advance_url)

    assert state["status"] == "completed"
    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "game.invalid_phase"


def test_create_game_rejects_legacy_players_as_validation_error(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/games",
        json={
            "seed": 42,
            "role_counts": DEFAULT_ROLE_COUNTS,
            "players": [{"id": "p1", "name": "Alice", "agent_type": "llm"}],
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "request.validation_failed"
    assert response.json()["errors"][0]["pointer"] == "/players"


def test_create_game_rejects_legacy_top_level_agent_as_validation_error(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/games",
        json={"role_counts": DEFAULT_ROLE_COUNTS, "agent": {"type": "dummy"}},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "request.validation_failed"
    assert response.json()["errors"][0]["pointer"] == "/agent"


def test_create_game_rejects_invalid_role_counts_as_validation_error(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/games",
        json={
            "role_counts": {"werewolf": -1},
        },
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "request.validation_failed"
    assert response.json()["errors"][0]["pointer"] == "/role_counts/werewolf"


def test_api_discussion_records_one_speech_per_alive_player_from_definition(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/games",
        json=_create_payload(seed=3),
    ).json()
    game_id = created["game_id"]

    after_night = client.post(f"/api/v1/games/{game_id}/advance").json()["state"]
    response = client.post(f"/api/v1/games/{game_id}/advance")

    assert response.status_code == 200
    speech_events = [
        item for item in response.json()["timeline"] if item["event_type"] == "speech_recorded"
    ]
    assert len(speech_events) == len(after_night["alive_player_ids"])
    assert all(item["payload"].get("message") for item in speech_events)


def test_create_game_validation_errors_use_problem_details(client: TestClient) -> None:
    response = client.post(
        "/api/v1/games",
        json={"seed": 1},
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "request.validation_failed"
    assert response.json()["errors"][0]["pointer"] == "/role_counts"


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
