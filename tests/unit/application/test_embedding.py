"""外部serviceなしのapplication組み込み境界を検証する。"""

from __future__ import annotations

from uuid import UUID

import pytest

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.application import (
    Actor,
    AdvanceGameCommand,
    AppError,
    ConfigError,
    ErrorCode,
    GameApplicationConfig,
    InMemoryGameRepository,
    InMemorySetupRepository,
    SingleTenantAccessPolicy,
    create_embedded_application,
)

USER_ID = "embedded-user"


def _config() -> GameApplicationConfig:
    return GameApplicationConfig(
        min_players=5,
        max_players=20,
        game_list_default_limit=20,
        game_list_max_limit=100,
        timeline_default_limit=100,
        timeline_max_limit=500,
    )


def test_embedded_application_runs_without_http_database_or_worker() -> None:
    catalog = build_setup_catalog()
    embedded = create_embedded_application(
        user_id=USER_ID,
        config=_config(),
        setup_catalog=catalog,
    )
    command = embedded.setups.prepare_create(
        catalog.require_document("standard_6"),
        seed=17,
        manual_player_id="p1",
        llm_mode="fake",
        deliberation_level="standard",
    )

    created = embedded.commands.execute(command)

    assert embedded.games.get(created.game_id, embedded.actor).game_id == created.game_id
    listed = embedded.games.list(embedded.actor)
    assert [game["game_id"] for game in listed.games] == [created.game_id]
    observation = embedded.games.observation(created.game_id, embedded.actor, "p1")
    assert observation.player_id == "p1"

    with pytest.raises(AppError) as reveal:
        embedded.games.reveal(created.game_id, embedded.actor)
    assert reveal.value.code is ErrorCode.AUTHORIZATION_FAILED


def test_embedded_application_explicitly_enables_trusted_reveal() -> None:
    catalog = build_setup_catalog()
    embedded = create_embedded_application(
        user_id=USER_ID,
        config=_config(),
        setup_catalog=catalog,
        allow_reveal=True,
    )
    created = embedded.commands.execute(
        embedded.setups.prepare_create(
            catalog.require_document("standard_6"),
            seed=19,
            manual_player_id=None,
            llm_mode="fake",
            deliberation_level="standard",
        )
    )

    assert embedded.games.reveal(created.game_id, embedded.actor).game_id == created.game_id


def test_embedded_application_rejects_non_boolean_reveal_flag() -> None:
    with pytest.raises(ConfigError, match="boolean"):
        create_embedded_application(
            user_id=USER_ID,
            config=_config(),
            setup_catalog=build_setup_catalog(),
            allow_reveal="false",  # type: ignore[arg-type]
        )


def test_embedded_application_rejects_unknown_create_llm_mode() -> None:
    with pytest.raises(ConfigError, match="create_llm_mode"):
        create_embedded_application(
            user_id=USER_ID,
            config=_config(),
            setup_catalog=build_setup_catalog(),
            create_llm_mode="unknown",  # type: ignore[arg-type]
        )


def test_embedded_application_keeps_state_in_injected_repositories() -> None:
    catalog = build_setup_catalog()
    games = InMemoryGameRepository(owner_user_id=USER_ID)
    setups = InMemorySetupRepository()
    first = create_embedded_application(
        user_id=USER_ID,
        config=_config(),
        setup_catalog=catalog,
        game_repository=games,
        setup_repository=setups,
        access_policy=SingleTenantAccessPolicy(user_id=USER_ID, repository=games),
    )
    created = first.commands.execute(
        first.setups.prepare_create(
            catalog.require_document("standard_6"),
            seed=23,
            manual_player_id=None,
            llm_mode="fake",
            deliberation_level="standard",
        )
    )

    second = create_embedded_application(
        user_id=USER_ID,
        config=_config(),
        setup_catalog=catalog,
        game_repository=games,
        setup_repository=setups,
        access_policy=SingleTenantAccessPolicy(user_id=USER_ID, repository=games),
    )

    assert second.games.get(created.game_id, second.actor).game_id == created.game_id
    assert games.get(UUID(created.game_id)) is not None


def test_embedded_application_requires_policy_for_external_game_repository() -> None:
    with pytest.raises(ConfigError, match="access_policy"):
        create_embedded_application(
            user_id=USER_ID,
            config=_config(),
            setup_catalog=build_setup_catalog(),
            game_repository=InMemoryGameRepository(owner_user_id=USER_ID),
        )


def test_embedded_application_does_not_share_default_state() -> None:
    catalog = build_setup_catalog()
    first = create_embedded_application(
        user_id=USER_ID,
        config=_config(),
        setup_catalog=catalog,
    )
    first.commands.execute(
        first.setups.prepare_create(
            catalog.require_document("standard_6"),
            seed=27,
            manual_player_id=None,
            llm_mode="fake",
            deliberation_level="standard",
        )
    )

    second = create_embedded_application(
        user_id=USER_ID,
        config=_config(),
        setup_catalog=catalog,
    )

    assert second.games.list(second.actor).games == []


def test_single_tenant_policy_rejects_other_users_and_automated_seats() -> None:
    catalog = build_setup_catalog()
    embedded = create_embedded_application(
        user_id=USER_ID,
        config=_config(),
        setup_catalog=catalog,
    )
    created = embedded.commands.execute(
        embedded.setups.prepare_create(
            catalog.require_document("standard_6"),
            seed=29,
            manual_player_id="p1",
            llm_mode="fake",
            deliberation_level="standard",
        )
    )

    with pytest.raises(AppError) as foreign:
        embedded.games.get(created.game_id, Actor("other-user"))
    assert foreign.value.code is ErrorCode.AUTHORIZATION_FAILED

    with pytest.raises(AppError) as automated:
        embedded.games.observation(created.game_id, embedded.actor, "p2")
    assert automated.value.code is ErrorCode.AUTHORIZATION_FAILED


def test_inline_advance_requires_an_explicit_version() -> None:
    embedded = create_embedded_application(
        user_id=USER_ID,
        config=_config(),
        setup_catalog=build_setup_catalog(),
    )

    with pytest.raises(ConfigError):
        embedded.commands.execute(AdvanceGameCommand(game_id="missing"))
