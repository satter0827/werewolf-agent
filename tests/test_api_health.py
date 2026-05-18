import os

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "werewolf_agent.interfaces.api.config.settings")
django = pytest.importorskip("django")
django.setup()
SimpleTestCase = pytest.importorskip("django.test").SimpleTestCase


class HealthEndpointTests(SimpleTestCase):
    def test_health_endpoint_returns_ok(self) -> None:
        response = self.client.get("/api/health/")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "werewolf-agent-api"}
