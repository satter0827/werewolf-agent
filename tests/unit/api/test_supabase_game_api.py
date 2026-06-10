from datetime import UTC, datetime, timedelta

import httpx

from werewolf_agent.api.supabase import SupabaseGameApi, SupabaseSession
from werewolf_agent.commons.configuration import AppSettings
from werewolf_agent.contracts.schemas import GameSetupOptionsResponse


def test_get_setup_options_reads_supabase_definition_item_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[{"payload": _setup_payload()}])

    api = SupabaseGameApi(
        AppSettings(
            _env_file=None,
            supabase_url="http://127.0.0.1:54321",
            supabase_publishable_key="anon-test",
        ),
        SupabaseSession(
            access_token="access",
            refresh_token="refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            user_id="user-1",
            email="",
            is_anonymous=True,
        ),
        transport=httpx.MockTransport(handler),
    )

    response = api.get_setup_options()

    assert response.default_setup_preset_id == "classic-six"
    assert requests[0].url.path == "/rest/v1/definition_items"
    assert "kind=eq.setup_options" in str(requests[0].url)


def _setup_payload() -> dict[str, object]:
    return GameSetupOptionsResponse(
        player_count={"min": 5, "max": 8, "default": 6},
        roles=[
            {
                "id": "villager",
                "name": "村人",
                "faction": "villagers",
                "abilities": [],
                "description": "推理で村を守ります",
                "difficulty": 1,
            }
        ],
        default_role_counts={"villager": 6},
        default_rules={
            "day_speech_limit_per_player": 1,
            "allow_self_vote": False,
            "allow_vote_revision": False,
            "allow_night_action_revision": False,
            "enable_first_night_attack": True,
            "enable_no_elimination_on_tie": True,
            "enable_random_elimination_on_tie": False,
            "allow_knight_self_guard": True,
            "allow_knight_repeat_guard": True,
            "allow_seer_self_inspect": False,
            "allow_werewolf_friendly_fire": False,
            "reveal_role_on_death": False,
        },
        default_scenario_id="misty-village",
        default_setup_preset_id="classic-six",
        default_agent_strategy_id="stable_fast",
        scenarios=[
            {
                "id": "misty-village",
                "name": "霧の村",
                "summary": "朝霧に包まれた村",
            }
        ],
        setup_presets=[
            {
                "id": "classic-six",
                "name": "定番の6人村",
                "scenario_id": "misty-village",
                "role_counts": {"villager": 6},
            }
        ],
        agent_strategies=[{"id": "stable_fast", "name": "標準", "description": "標準的な進行"}],
    ).model_dump(mode="json")
