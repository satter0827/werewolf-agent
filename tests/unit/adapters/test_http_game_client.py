import httpx
import pytest
import respx

from werewolf_agent.adapters.application_bridge import (
    build_game_definitions,
    build_player_setup_definitions,
)
from werewolf_agent.adapters.http import HttpPublicClient
from werewolf_agent.application.setup_document import setup_document_from_preset
from werewolf_agent.contracts import AppError, ErrorCode
from werewolf_agent.contracts.schemas import GameSetupDocumentRequest, GameSetupOptionsResponse
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

    client = HttpPublicClient(
        AppSettings(
            _env_file=None,
            api_base_url="http://api.test",
            supabase_url="http://auth.test",
            supabase_publishable_key="anon-test",
        ),
        transport=httpx.MockTransport(handler),
    )

    runtime = client.get_runtime_config()
    response = runtime.setup

    assert runtime.limits.message_max_chars == 120
    assert response.default_setup_preset_id == "classic-six"
    assert requests[0].url.path == "/api/v1/config"
    assert "/rest/v1/" not in str(requests[0].url)


def test_validate_setup_posts_the_complete_document_to_public_api() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "player_count": 6,
                "theme_id": "classic_village",
                "theme_name": "古い村",
                "role_ids": ["knight", "seer", "villager", "werewolf"],
                "ability_ids": ["guard", "inspect", "night_attack", "pack_knowledge"],
                "setup_checksum": "a" * 64,
                "mechanics_checksum": "b" * 64,
            },
        )

    settings = AppSettings(
        _env_file=None,
        api_base_url="http://api.test",
        supabase_url="http://auth.test",
        supabase_publishable_key="anon-test",
    )
    setup = setup_document_from_preset(
        "standard_6",
        build_game_definitions(settings),
        build_player_setup_definitions(settings),
    )
    client = HttpPublicClient(settings, transport=httpx.MockTransport(handler))

    result = client.validate_setup(
        GameSetupDocumentRequest.model_validate(setup.model_dump(mode="json"))
    )

    assert result.player_count == 6
    assert captured[0].method == "POST"
    assert captured[0].url.path == "/api/v1/setups/validate"


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


def _client() -> HttpPublicClient:
    return HttpPublicClient(
        AppSettings(
            _env_file=None,
            api_base_url="http://api.test",
            supabase_url="http://auth.test",
            supabase_publishable_key="anon-test",
        ),
    )


def _setup_payload() -> dict[str, object]:
    return GameSetupOptionsResponse(
        player_count={"min": 5, "max": 8, "default": 6},
        roles=[
            {
                "id": "villager",
                "name": "村人",
                "identity_faction": "village",
                "victory_team": "village",
                "objective": "人狼を排除します",
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
            "vote_tie_resolution": "no_elimination",
            "wolf_attack_tie_resolution": "random_target",
            "seer_result_detail": "faction",
            "medium_result_detail": "faction",
            "starting_phase": "night",
            "allow_knight_self_guard": True,
            "allow_knight_repeat_guard": True,
            "allow_seer_self_inspect": False,
            "allow_werewolf_friendly_fire": False,
            "reveal_role_on_death": False,
        },
        default_scenario_id="misty-village",
        default_setup_preset_id="classic-six",
        scenarios=[
            {
                "id": "misty-village",
                "name": "霧の村",
                "summary": "朝霧に包まれた村",
                "premise": "朝霧に包まれた村で議論します",
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
    ).model_dump(mode="json")
