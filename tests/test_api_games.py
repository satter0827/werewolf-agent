import json
import os
from uuid import uuid4

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "werewolf_agent.interfaces.api.config.settings")
django = pytest.importorskip("django")
django.setup()

setup_databases = pytest.importorskip("django.test.utils").setup_databases
teardown_databases = pytest.importorskip("django.test.utils").teardown_databases
TestCase = pytest.importorskip("django.test").TestCase

_database_config = None


def setUpModule() -> None:
    global _database_config
    _database_config = setup_databases(verbosity=0, interactive=False)


def tearDownModule() -> None:
    if _database_config is not None:
        teardown_databases(_database_config, verbosity=0)


def _create_payload() -> dict[str, object]:
    return {
        "seed": 42,
        "players": [
            {"id": "p1", "name": "Alice", "agent_type": "dummy"},
            {"id": "p2", "name": "Bob", "agent_type": "dummy"},
            {"id": "p3", "name": "Carol", "agent_type": "dummy"},
            {"id": "p4", "name": "Dave", "agent_type": "dummy"},
            {"id": "p5", "name": "Eve", "agent_type": "dummy"},
        ],
    }


class ApiGamesEndpointTests(TestCase):
    def test_default_ruleset_endpoint_returns_mvp_metadata(self) -> None:
        response = self.client.get("/api/rulesets/default/")

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
        assert payload["agent_types"] == [{"id": "dummy", "name": "Dummy Agent"}]

    def test_create_game_returns_public_state_without_private_fields(self) -> None:
        response = self.client.post(
            "/api/games/",
            data=json.dumps(_create_payload()),
            content_type="application/json",
        )

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

    def test_steps_complete_game_and_events_are_public_only(self) -> None:
        create_response = self.client.post(
            "/api/games/",
            data=json.dumps({"player_count": 6, "seed": 1}),
            content_type="application/json",
        )
        game_id = create_response.json()["game_id"]

        state = create_response.json()["state"]
        event_payload = {"events": []}
        for _ in range(32):
            step_response = self.client.post(f"/api/games/{game_id}/steps/")
            assert step_response.status_code == 200
            step_payload = step_response.json()
            state = step_payload["state"]
            event_payload = self.client.get(f"/api/games/{game_id}/events/?after=0").json()
            if state["status"] == "completed":
                break

        assert state["status"] == "completed"
        assert state["winner"] in {"villagers", "werewolves"}
        assert event_payload["events"]
        assert all(event["visibility"] == "public" for event in event_payload["events"])
        assert "role" not in json.dumps(event_payload)
        assert "private_state" not in json.dumps(event_payload)

    def test_advance_alias_uses_same_step_contract(self) -> None:
        created = self.client.post(
            "/api/games/",
            data=json.dumps({"player_count": 5, "seed": 2}),
            content_type="application/json",
        ).json()

        response = self.client.post(f"/api/games/{created['game_id']}/advance/")

        assert response.status_code == 200
        assert response.json()["game_id"] == created["game_id"]
        assert response.json()["state"]["version"] == 2

    def test_finished_game_advance_returns_problem_details(self) -> None:
        created = self.client.post(
            "/api/games/",
            data=json.dumps({"player_count": 6, "seed": 1}),
            content_type="application/json",
        ).json()
        advance_url = f"/api/games/{created['game_id']}/steps/"
        state = created["state"]
        for _ in range(32):
            response = self.client.post(advance_url)
            state = response.json()["state"]
            if state["status"] == "completed":
                break

        response = self.client.post(advance_url)

        assert state["status"] == "completed"
        assert response.status_code == 409
        assert response["Content-Type"].startswith("application/problem+json")
        assert response.json()["code"] == "game.invalid_phase"

    def test_create_game_rejects_unsupported_agent_type_as_game_action_error(self) -> None:
        payload = _create_payload()
        payload["players"][0]["agent_type"] = "llm"

        response = self.client.post(
            "/api/games/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 422
        assert response.json()["code"] == "game.invalid_action"

    def test_create_game_validation_errors_use_problem_details(self) -> None:
        response = self.client.post(
            "/api/games/",
            data=json.dumps({"players": [{"id": "p1", "agent_type": "dummy"}]}),
            content_type="application/json",
        )

        assert response.status_code == 400
        assert response["Content-Type"].startswith("application/problem+json")
        assert response.json()["code"] == "request.validation_failed"
        assert response.json()["errors"][0]["pointer"] == "/players/0/name"

    def test_missing_game_returns_problem_details(self) -> None:
        response = self.client.get(f"/api/games/{uuid4()}/")

        assert response.status_code == 404
        assert response["Content-Type"].startswith("application/problem+json")
        assert response.json()["code"] == "not_found"
