"""実FastAPI process identity contract。"""

from fastapi.testclient import TestClient

from werewolf_agent.api.bootstrap import create_app
from werewolf_agent.settings import AppSettings


def test_health_identifies_exact_app_instance_and_public_configuration() -> None:
    first = TestClient(create_app(AppSettings(_env_file=None)))
    second = TestClient(create_app(AppSettings(_env_file=None)))

    first_health = first.get("/health").json()
    repeated = first.get("/health").json()
    second_health = second.get("/health").json()

    assert first_health == repeated
    assert first_health["instance_id"] != second_health["instance_id"]
    assert len(first_health["config_fingerprint"]) == 64
    assert first_health["started_at"].endswith("+00:00")
