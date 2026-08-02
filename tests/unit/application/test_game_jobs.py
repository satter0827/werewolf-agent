from typing import cast

import pytest

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.application.actor import Actor
from werewolf_agent.application.errors import AppError, ConfigError, ErrorCode
from werewolf_agent.application.models import CreateGameCommand, GameApplicationConfig
from werewolf_agent.application.ports import SetupRepository
from werewolf_agent.application.setup_facade import SetupApplication
from werewolf_agent.application.setup_options import prepare_create_command, preview_players
from werewolf_agent.setup import GameSetupDocument, checksum_payload


def test_create_command_contains_a_complete_resolved_setup_and_generated_players(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = build_setup_catalog().require_document("standard_6")
    monkeypatch.setattr("werewolf_agent.application.setup_options.secrets.randbits", lambda _n: 99)

    command = prepare_create_command(
        setup,
        seed=17,
        manual_player_id="p1",
        llm_mode="fake",
        deliberation_level="standard",
    )

    assert command.seed == 99
    assert command.setup == setup
    assert [player.player_id for player in command.players] == [f"p{i}" for i in range(1, 7)]
    assert command.players[0].reasoning_style
    assert command.setup_checksum == checksum_payload(setup.to_mapping())
    assert command.mechanics_checksum == checksum_payload(setup.mechanics.to_mapping())
    assert command.roster_checksum == checksum_payload(
        [player.public_payload() for player in command.players]
    )
    assert command.rule_pack_provider_id == "core"
    assert command.model_dump(mode="json")["setup"] == setup.to_mapping()
    queued_payload = command.model_dump(mode="json", exclude_none=True)
    assert CreateGameCommand.model_validate(queued_payload).setup == setup


def test_create_command_preserves_an_explicit_rule_pack_provider() -> None:
    """Queueへ送る前に選択したprovider IDを一局のcommandへ固定する."""
    setup = build_setup_catalog().require_document("standard_6")

    command = prepare_create_command(
        setup,
        seed=17,
        manual_player_id=None,
        llm_mode="fake",
        deliberation_level="standard",
        rule_pack_provider_id="experimental",
    )

    assert command.rule_pack_provider_id == "experimental"


def test_preview_omits_private_strategy_and_role() -> None:
    setup = build_setup_catalog().require_document("standard_6")

    preview = preview_players(setup, seed=17)
    payload = preview.model_dump(mode="json")

    assert payload["players"]
    assert all("reasoning_style" not in player for player in payload["players"])
    assert all("role" not in player for player in payload["players"])

    command = prepare_create_command(
        setup,
        seed=preview.seed,
        manual_player_id=None,
        llm_mode="fake",
        deliberation_level="standard",
    )
    assert preview.roster_checksum == command.roster_checksum


def test_public_roster_seed_does_not_control_private_game_randomness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = build_setup_catalog().require_document("standard_6")
    private_seeds = iter((101, 202))
    monkeypatch.setattr(
        "werewolf_agent.application.setup_options.secrets.randbits",
        lambda _n: next(private_seeds),
    )

    first = prepare_create_command(
        setup,
        seed=17,
        manual_player_id=None,
        llm_mode="fake",
        deliberation_level="standard",
    )
    second = prepare_create_command(
        setup,
        seed=17,
        manual_player_id=None,
        llm_mode="fake",
        deliberation_level="standard",
    )

    assert first.roster_checksum == second.roster_checksum
    assert first.seed == 101
    assert second.seed == 202
    assert [player.reasoning_style for player in first.players] != [
        player.reasoning_style for player in second.players
    ]


def test_anonymous_actor_cannot_persist_a_setup() -> None:
    setup = build_setup_catalog().require_document("standard_6")
    application = SetupApplication(
        build_setup_catalog(),
        GameApplicationConfig(
            min_players=5,
            max_players=20,
            game_list_default_limit=20,
            game_list_max_limit=100,
            timeline_default_limit=100,
            timeline_max_limit=500,
        ),
        cast(SetupRepository, object()),
    )

    with pytest.raises(AppError) as raised:
        application.create(
            Actor(user_id="anonymous", is_anonymous=True),
            display_name="保存不可",
            document=setup,
        )

    assert raised.value.code is ErrorCode.AUTHORIZATION_FAILED


def test_setup_runtime_limits_are_checked_before_preview_or_queue_preparation() -> None:
    payload = build_setup_catalog().require_document("standard_6").to_mapping()
    payload["mechanics"]["role_counts"]["villager"] = 1
    setup = GameSetupDocument.from_mapping(payload)
    application = SetupApplication(
        build_setup_catalog(),
        GameApplicationConfig(
            min_players=5,
            max_players=8,
            game_list_default_limit=20,
            game_list_max_limit=100,
            timeline_default_limit=100,
            timeline_max_limit=500,
        ),
        cast(SetupRepository, object()),
    )

    with pytest.raises(ConfigError, match="player_count must be between 5 and 8"):
        application.preview(setup, seed=1)
    with pytest.raises(ConfigError, match="player_count must be between 5 and 8"):
        application.prepare_create(
            setup,
            seed=1,
            manual_player_id=None,
            llm_mode="fake",
            deliberation_level="standard",
        )
