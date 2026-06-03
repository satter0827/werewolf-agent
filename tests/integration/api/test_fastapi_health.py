from fastapi.testclient import TestClient

from werewolf_agent.interface.api.app import create_app
from werewolf_agent.interface.runtime import AppSettings


def test_fastapi_surface_is_health_only() -> None:
    app = create_app(AppSettings(_env_file=None))

    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_fastapi_game_routes_are_not_exposed() -> None:
    app = create_app(AppSettings(_env_file=None))

    response = TestClient(app).get("/api/v1/games")

    assert response.status_code == 404
