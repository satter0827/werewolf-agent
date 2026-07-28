import httpx

from werewolf_agent.adapters.http.public_client import HttpPublicClient
from werewolf_agent.settings import AppSettings


def test_public_client_reads_setup_catalog() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/setup-catalog"
        return httpx.Response(
            200,
            json={
                "player_count": {"min": 5, "max": 20},
                "recommended_template_id": "standard_6",
                "template_order": ["standard_6"],
                "templates": {"standard_6": {"name": "標準", "summary": "6人"}},
                "ability_kinds": [
                    "attack",
                    "inspect",
                    "protect",
                    "eliminate",
                    "knowledge",
                    "death_reaction",
                    "immunity",
                    "vulnerability",
                ],
            },
        )

    client = HttpPublicClient(AppSettings(_env_file=None), transport=httpx.MockTransport(handler))

    assert client.get_setup_catalog().recommended_template_id == "standard_6"
