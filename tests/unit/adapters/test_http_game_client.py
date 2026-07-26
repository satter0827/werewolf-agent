from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from werewolf_agent.adapters.http import HttpGameClient
from werewolf_agent.adapters.supabase import SupabaseSession
from werewolf_agent.contracts import AppError, ErrorCode
from werewolf_agent.contracts.schemas import GameSetupOptionsResponse
from werewolf_agent.settings import AppSettings


def test_get_setup_options_uses_public_api_config_not_supabase_data_api() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "contract_version": "v1",
                "config_revision": "test",
                "setup": _setup_payload(),
                "limits": {
                    "game_min_players": 5,
                    "game_max_players": 8,
                    "message_max_chars": 120,
                    "game_list_page_size": 20,
                    "timeline_page_size": 100,
                },
                "features": {
                    "authentication": True,
                    "paid_llm_for_members": True,
                    "admin_reveal": True,
                    "admin_replay": True,
                },
                "ui": {
                    "theme_id": "dawn-table",
                    "spacing_unit": 4,
                    "desktop_breakpoint": 980,
                    "motion": "system",
                    "default_manual_player_id": "player-1",
                    "default_setup_seed": "1",
                    "operation_poll_interval_ms": 250,
                    "operation_poll_timeout_ms": 60_000,
                },
            },
        )

    client = HttpGameClient(
        AppSettings(
            _env_file=None,
            api_base_url="http://api.test",
            supabase_url="http://auth.test",
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

    runtime = client.get_runtime_config()
    response = client.get_setup_options()

    assert runtime.limits.message_max_chars == 120
    assert response.default_setup_preset_id == "classic-six"
    assert requests[0].url.path == "/api/v1/config"
    assert "/rest/v1/" not in str(requests[0].url)


@respx.mock
def test_timeout_is_mapped_to_retryable_api_unavailable() -> None:
    respx.get("http://api.test/health").mock(side_effect=httpx.ReadTimeout("slow"))

    with pytest.raises(AppError) as captured:
        _client().health()

    assert captured.value.code is ErrorCode.API_UNAVAILABLE
    assert captured.value.retryable is True


@respx.mock
def test_malformed_success_response_is_rejected_by_schema() -> None:
    respx.get("http://api.test/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    with pytest.raises(AppError) as captured:
        _client().health()

    assert captured.value.code is ErrorCode.INTERNAL_UNEXPECTED


def _client() -> HttpGameClient:
    return HttpGameClient(
        AppSettings(
            _env_file=None,
            api_base_url="http://api.test",
            supabase_url="http://auth.test",
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
    )


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
