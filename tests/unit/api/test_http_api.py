"""HTTP boundary contract and security tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from werewolf_agent.api.bootstrap import create_app
from werewolf_agent.api.dependencies import RequestServices, get_services
from werewolf_agent.application.operations import QueuedOperation
from werewolf_agent.contracts import ErrorCode
from werewolf_agent.security.principal import Principal
from werewolf_agent.settings import AppSettings

NOW = datetime(2026, 7, 24, tzinfo=UTC)


class FakeAuthenticator:
    """Resolve test principals without accepting client identity fields."""

    def authenticate(self, token: str) -> Principal:
        if token == "guest":
            return Principal(user_id="guest-user", is_anonymous=True, is_admin=False)
        if token == "admin":
            return Principal(user_id="admin-user", is_anonymous=False, is_admin=True)
        return Principal(user_id="member-user", is_anonymous=False, is_admin=False)


class FakeOperations:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, Any]] = []

    def enqueue(self, **values: Any) -> QueuedOperation:
        self.enqueued.append(values)
        return QueuedOperation(
            operation_id="operation-1",
            operation_type=str(values["operation_type"]),
            status="queued",
            owner_user_id=str(values["owner_user_id"]),
            game_id=values.get("game_id"),
            expected_version=values.get("expected_version"),
            result=None,
            error=None,
            created_at=NOW,
            updated_at=NOW,
        )

    def get(self, operation_id: str, *, owner_user_id: str) -> QueuedOperation | None:
        if operation_id != "operation-1" or owner_user_id != "member-user":
            return None
        return QueuedOperation(
            operation_id=operation_id,
            operation_type="advance_game",
            status="running",
            owner_user_id=owner_user_id,
            game_id="00000000-0000-0000-0000-000000000001",
            expected_version=2,
            result=None,
            error=None,
            created_at=NOW,
            updated_at=NOW,
        )


class FakeAccess:
    def require_game_access(self, game_id: str, *, user_id: str) -> None:
        del game_id, user_id

    def require_player_access(self, game_id: str, player_id: str, *, user_id: str) -> None:
        del game_id, player_id, user_id


class FakeGames:
    def __init__(self, operations: FakeOperations, access: FakeAccess) -> None:
        self.operations = operations
        self.access = access

    def enqueue_create(self, actor: Any, **values: Any) -> QueuedOperation:
        return self.operations.enqueue(
            operation_type="create_game",
            owner_user_id=actor.user_id,
            **values,
        )

    def enqueue_action(self, game_id: str, actor: Any, **values: Any) -> QueuedOperation:
        player_id = str(values.pop("player_id"))
        self.access.require_player_access(game_id, player_id, user_id=actor.user_id)
        return self.operations.enqueue(
            operation_type="submit_action",
            owner_user_id=actor.user_id,
            game_id=game_id,
            player_id=player_id,
            llm_mode=None,
            **values,
        )

    def enqueue_advance(self, game_id: str, actor: Any, **values: Any) -> QueuedOperation:
        self.access.require_game_access(game_id, user_id=actor.user_id)
        return self.operations.enqueue(
            operation_type="advance_game",
            owner_user_id=actor.user_id,
            game_id=game_id,
            request_payload={},
            llm_mode=None,
            **values,
        )

    def operation(self, operation_id: str, actor: Any) -> QueuedOperation | None:
        return self.operations.get(operation_id, owner_user_id=actor.user_id)


class FakeDiagnostics:
    def operation(self, operation_id: str) -> dict[str, Any] | None:
        if operation_id != "operation-1":
            return None
        return {
            "operation_id": operation_id,
            "operation_type": "advance_game",
            "status": "running",
            "game_id": "00000000-0000-0000-0000-000000000001",
            "attempt_count": 1,
            "worker_id": "worker-1",
            "created_at": NOW,
            "started_at": NOW,
            "completed_at": None,
            "error_payload": None,
        }

    def traces(self, game_id: str, *, limit: int) -> list[dict[str, Any]]:
        del limit
        return [
            {
                "invocation_id": "00000000-0000-0000-0000-000000000010",
                "game_id": game_id,
                "operation_id": "00000000-0000-0000-0000-000000000020",
                "state_version": 2,
                "provider": "openai",
                "model": "configured-model",
                "player_id": "player-1",
                "phase": "day",
                "day": 1,
                "prompt_hash": "a" * 64,
                "parsed_decision": {"type": "speech"},
                "error_payload": None,
                "latency_ms": 10.0,
                "created_at": NOW,
            }
        ]

    def usage(self, game_id: str) -> dict[str, Any]:
        return {
            "game_id": game_id,
            "invocation_count": 1,
            "input_tokens": 10,
            "output_tokens": 5,
            "cost_micros": 0,
        }


def _client() -> tuple[TestClient, FakeOperations]:
    app = create_app()
    operations = FakeOperations()
    access = FakeAccess()
    services = RequestServices(  # type: ignore[arg-type]
        games=FakeGames(operations, access),
        message_max_chars=200,
        diagnostics=FakeDiagnostics(),
    )
    app.state.authenticator = FakeAuthenticator()
    app.dependency_overrides[get_services] = lambda: services
    return TestClient(app, raise_server_exceptions=False), operations


def test_public_config_contains_verifiable_values_without_secrets() -> None:
    client, _ = _client()

    response = client.get("/api/v1/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "v1"
    assert payload["config_revision"]
    assert payload["ui"]["theme_id"] == "dawn-table"
    assert payload["ui"]["desktop_breakpoint"] == 980
    assert payload["features"]["admin_reveal"] is True
    serialized = response.text.lower()
    for forbidden in ("api_key", "service_key", "db_dsn", "password", "token"):
        assert forbidden not in serialized


def test_api_responses_are_not_cached_or_embedded() -> None:
    client, _ = _client()

    response = client.get("/api/v1/config")

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_problem_responses_use_the_same_security_headers() -> None:
    client, _ = _client()

    response = client.get("/api/v1/games", headers={"Authorization": "invalid"})

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_public_config_uses_validated_ui_settings() -> None:
    app = create_app(
        AppSettings(
            _env_file=None,
            ui_spacing_unit=6,
            ui_desktop_breakpoint=1024,
            ui_motion="reduced",
            ui_operation_poll_interval_ms=500,
        )
    )

    payload = TestClient(app).get("/api/v1/config").json()

    assert payload["ui"]["spacing_unit"] == 6
    assert payload["ui"]["desktop_breakpoint"] == 1024
    assert payload["ui"]["motion"] == "reduced"
    assert payload["ui"]["operation_poll_interval_ms"] == 500


def test_api_documentation_is_not_part_of_the_default_public_surface() -> None:
    client, _ = _client()

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_api_documentation_can_be_enabled_for_development() -> None:
    app = create_app(AppSettings(_env_file=None, api_docs_enabled=True))

    assert TestClient(app).get("/docs").status_code == 200
    assert TestClient(app).get("/openapi.json").status_code == 200


def test_admin_reveal_feature_flag_matches_runtime_behavior() -> None:
    client, _ = _client()
    services = client.app.dependency_overrides[get_services]()
    client.app.dependency_overrides[get_services] = lambda: RequestServices(
        games=services.games,
        message_max_chars=services.message_max_chars,
        diagnostics=services.diagnostics,
        reveal_api_enabled=False,
    )

    response = client.get(
        "/api/v1/admin/games/00000000-0000-0000-0000-000000000001/reveal",
        headers={"Authorization": "Bearer admin"},
    )

    assert response.status_code == 503
    assert response.json()["code"] == ErrorCode.API_UNAVAILABLE.value


def test_guest_creation_is_forced_to_fake_llm_mode() -> None:
    client, operations = _client()

    response = client.post(
        "/api/v1/games",
        headers={
            "Authorization": "Bearer guest",
            "Idempotency-Key": "create-game-001",
        },
        json={
            "seed": 1,
            "role_counts": {"werewolf": 1, "seer": 1, "knight": 1, "villager": 2},
        },
    )

    assert response.status_code == 202
    assert operations.enqueued[-1]["llm_mode"] == "fake"
    assert "provider" not in operations.enqueued[-1]["request_payload"]
    assert "model" not in operations.enqueued[-1]["request_payload"]


def test_member_creation_is_forced_to_paid_llm_mode() -> None:
    client, operations = _client()

    response = client.post(
        "/api/v1/games",
        headers={
            "Authorization": "Bearer member",
            "Idempotency-Key": "create-game-002",
        },
        json={
            "seed": 1,
            "role_counts": {"werewolf": 1, "seer": 1, "knight": 1, "villager": 2},
        },
    )

    assert response.status_code == 202
    assert operations.enqueued[-1]["llm_mode"] == "paid"


def test_existing_game_commands_do_not_use_the_current_principal_llm_mode() -> None:
    client, operations = _client()
    headers = {
        "Authorization": "Bearer member",
        "Idempotency-Key": "advance-game-001",
    }

    response = client.post(
        "/api/v1/games/00000000-0000-0000-0000-000000000001/advance",
        headers=headers,
        json={"expected_version": 1},
    )

    assert response.status_code == 202
    assert operations.enqueued[-1]["llm_mode"] is None


def test_command_requires_idempotency_key() -> None:
    client, _ = _client()

    response = client.post(
        "/api/v1/games",
        headers={"Authorization": "Bearer member"},
        json={
            "seed": 1,
            "role_counts": {"werewolf": 1, "seer": 1, "knight": 1, "villager": 2},
        },
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "request.validation_failed"


def test_operation_is_not_visible_to_another_user() -> None:
    client, _ = _client()

    response = client.get(
        "/api/v1/operations/operation-1",
        headers={"Authorization": "Bearer guest"},
    )

    assert response.status_code == 404
    assert "owner_user_id" not in response.text


def test_player_action_rejects_text_beyond_the_public_runtime_limit() -> None:
    client, operations = _client()

    response = client.post(
        "/api/v1/games/00000000-0000-0000-0000-000000000001/actions",
        headers={
            "Authorization": "Bearer member",
            "Idempotency-Key": "long-message-001",
        },
        json={
            "player_id": "player-1",
            "expected_version": 1,
            "action": {"type": "speech", "message": "あ" * 201},
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "request.validation_failed"
    assert operations.enqueued == []


def test_timeline_limit_is_part_of_the_openapi_contract() -> None:
    client, _ = _client()

    parameters = client.app.openapi()["paths"]["/api/v1/games/{game_id}/timeline"]["get"][
        "parameters"
    ]

    assert any(
        parameter["name"] == "limit" and parameter["in"] == "query" for parameter in parameters
    )


def test_openapi_contains_no_secret_contract_fields() -> None:
    client, _ = _client()

    document = client.app.openapi()
    serialized = str(document).lower()

    for forbidden in ("openai_api_key", "service_role_key", "refresh_token", "db_dsn"):
        assert forbidden not in serialized
    assert "HTTPValidationError" not in serialized
    assert "ValidationError" not in serialized

    create_responses = document["paths"]["/api/v1/games"]["post"]["responses"]
    assert "422" not in create_responses
    assert create_responses["400"]["content"]["application/problem+json"]["schema"] == {
        "$ref": "#/components/schemas/ProblemDetails"
    }


def test_checked_in_openapi_matches_the_runtime_contract() -> None:
    checked_in = json.loads(
        (Path(__file__).resolve().parents[3] / "contracts" / "openapi.json").read_text(
            encoding="utf-8"
        )
    )

    assert checked_in == create_app().openapi()


def test_chunked_body_cannot_bypass_the_size_limit() -> None:
    app = create_app(AppSettings(_env_file=None, api_max_body_bytes=1024))
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/v1/games",
        headers={
            "Authorization": "Bearer invalid",
            "Idempotency-Key": "oversized-request",
        },
        content=(chunk for chunk in (b"x" * 700, b"y" * 700)),
    )

    assert response.status_code == 413
    assert response.json()["code"] == "request.body_too_large"


def test_understated_content_length_cannot_bypass_the_size_limit() -> None:
    app = create_app(AppSettings(_env_file=None, api_max_body_bytes=1024))
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/v1/games",
        headers={
            "Authorization": "Bearer invalid",
            "Content-Length": "1",
            "Idempotency-Key": "undersized-header",
        },
        content=b"x" * 1400,
    )

    assert response.status_code == 413
    assert response.json()["code"] == "request.body_too_large"


def test_admin_diagnostics_are_isolated_and_exclude_prompt_content() -> None:
    client, _ = _client()

    forbidden = client.get(
        "/api/v1/admin/operations/operation-1",
        headers={"Authorization": "Bearer member"},
    )
    operation = client.get(
        "/api/v1/admin/operations/operation-1",
        headers={"Authorization": "Bearer admin"},
    )
    traces = client.get(
        "/api/v1/admin/games/00000000-0000-0000-0000-000000000001/llm-traces",
        headers={"Authorization": "Bearer admin"},
    )
    usage = client.get(
        "/api/v1/admin/games/00000000-0000-0000-0000-000000000001/llm-usage",
        headers={"Authorization": "Bearer admin"},
    )

    assert forbidden.status_code == 403
    assert operation.status_code == 200
    assert traces.status_code == 200
    assert "prompt_messages" not in traces.text
    assert "raw_response" not in traces.text
    assert usage.json()["input_tokens"] == 10
