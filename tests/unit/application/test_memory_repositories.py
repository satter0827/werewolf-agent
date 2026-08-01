"""In-memory repositoryがapplication persistence契約を満たすことを検証する。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from uuid import UUID

import pytest

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.application import (
    InMemoryGameRepository,
    InMemorySetupRepository,
    assert_game_repository_contract,
    assert_setup_repository_contract,
)
from werewolf_agent.application.errors import AppError, ErrorCode, GameNotFoundError, GamePhaseError
from werewolf_agent.application.models import GameEventCreate, GameRecordCreate, GameRecordUpdate

OWNER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_OWNER_ID = "22222222-2222-2222-2222-222222222222"
GAME_ID = UUID("33333333-3333-3333-3333-333333333333")
STARTED_AT = datetime(2026, 8, 1, tzinfo=UTC)


class _Clock:
    def __init__(self) -> None:
        self.value = STARTED_AT

    def __call__(self) -> datetime:
        current = self.value
        self.value += timedelta(seconds=1)
        return current


class _FalseyClock(_Clock):
    def __bool__(self) -> bool:
        return False


def _game_create() -> GameRecordCreate:
    return GameRecordCreate(
        id=GAME_ID,
        status="running",
        phase="night",
        day=1,
        seed=42,
        config={"llm_mode": "fake"},
        public_state={
            "players": [{"id": "p1"}, {"id": "p2"}],
            "summary": {"alive_count": 2},
            "scenario_id": "standard_6",
            "scenario_name": "標準6人村",
            "theme": {"id": "standard"},
        },
        private_state={"secret": ["werewolf"]},
        pending_actions={},
        version=1,
    )


def _game_update(*, version: int = 2) -> GameRecordUpdate:
    return GameRecordUpdate(
        id=GAME_ID,
        status="running",
        phase="day_discussion",
        day=2,
        public_state={
            "players": [{"id": "p1"}, {"id": "p2"}],
            "summary": {"alive_count": 1},
            "winner": None,
        },
        private_state={"secret": ["werewolf", "seer"]},
        pending_actions={"p1": {"type": "speech"}},
        version=version,
    )


def test_game_repository_persists_isolated_snapshots_and_updates() -> None:
    repository = InMemoryGameRepository(owner_user_id=OWNER_ID, clock=_Clock())

    created = repository.create(_game_create())
    created.public_state["players"].append({"id": "injected"})

    persisted = repository.get(GAME_ID)
    assert persisted is not None
    assert len(persisted.public_state["players"]) == 2

    updated = repository.save(_game_update())
    assert updated.version == 2
    assert updated.seed == 42
    assert updated.config == {"llm_mode": "fake"}
    assert updated.created_at == STARTED_AT
    assert updated.updated_at > updated.created_at


def test_memory_repositories_honor_falsey_injected_clocks() -> None:
    game_repository = InMemoryGameRepository(owner_user_id=OWNER_ID, clock=_FalseyClock())
    setup_repository = InMemorySetupRepository(clock=_FalseyClock())
    document = build_setup_catalog().require_document("standard_6")

    game = game_repository.create(_game_create())
    setup = setup_repository.create(
        owner_user_id=OWNER_ID,
        display_name="実験設定",
        document=document,
        setup_checksum="a" * 64,
        mechanics_checksum="b" * 64,
        max_setups=100,
    )

    assert game.created_at == STARTED_AT
    assert setup.created_at == STARTED_AT


def test_game_repository_satisfies_shared_contract() -> None:
    assert_game_repository_contract(
        InMemoryGameRepository(owner_user_id=OWNER_ID, clock=_Clock()),
        game_id=GAME_ID,
    )


def test_game_repository_rejects_missing_and_stale_updates() -> None:
    repository = InMemoryGameRepository(owner_user_id=OWNER_ID)

    with pytest.raises(GameNotFoundError):
        repository.save(_game_update())

    repository.create(_game_create())
    with pytest.raises(GamePhaseError):
        repository.save(_game_update(version=3))


def test_game_repository_serializes_the_complete_transaction_unit() -> None:
    repository = InMemoryGameRepository(owner_user_id=OWNER_ID)
    first_entered = Event()
    release_first = Event()
    second_entered = Event()

    def hold_first_transaction() -> None:
        with repository.transaction():
            first_entered.set()
            assert release_first.wait(timeout=2)

    def enter_second_transaction() -> None:
        assert first_entered.wait(timeout=2)
        with repository.transaction():
            second_entered.set()

    first = Thread(target=hold_first_transaction)
    second = Thread(target=enter_second_transaction)
    first.start()
    second.start()
    assert first_entered.wait(timeout=2)
    assert not second_entered.wait(timeout=0.05)
    release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)
    assert not first.is_alive()
    assert not second.is_alive()
    assert second_entered.is_set()


def test_game_repository_projects_owner_scoped_summary_and_public_turns() -> None:
    repository = InMemoryGameRepository(owner_user_id=OWNER_ID, clock=_Clock())
    repository.create(_game_create())

    events = repository.append_events(
        GAME_ID,
        [
            GameEventCreate(visibility="debug", event_type="private", payload={"x": 1}),
            GameEventCreate(
                visibility="public",
                phase="night",
                day=1,
                actor_id="p1",
                event_type="speech",
                payload={"message": "hello"},
            ),
        ],
    )

    assert [event.sequence for event in events] == [1, 2]
    assert repository.latest_public_turn_sequence(GAME_ID) == 1
    turns = repository.list_public_turns(GAME_ID, after=0, limit=10)
    assert len(turns) == 1
    assert turns[0].event_sequence == 2
    assert turns[0].version == 1
    assert turns[0].payload == {"message": "hello"}

    assert (
        repository.list_game_summaries(
            user_id=OTHER_OWNER_ID,
            status=None,
            limit=10,
            offset=0,
        )
        == []
    )
    summaries = repository.list_game_summaries(
        user_id=OWNER_ID,
        status="running",
        limit=10,
        offset=0,
    )
    assert len(summaries) == 1
    assert summaries[0].player_count == 2
    assert summaries[0].alive_count == 2
    assert summaries[0].turn_count == 1


def test_setup_repository_preserves_owner_and_immutable_revisions() -> None:
    repository = InMemorySetupRepository(clock=_Clock())
    document = build_setup_catalog().require_document("standard_6")

    first = repository.create(
        owner_user_id=OWNER_ID,
        display_name="実験設定",
        document=document,
        setup_checksum="a" * 64,
        mechanics_checksum="b" * 64,
        max_setups=100,
    )
    second = repository.add_revision(
        first.setup_id,
        owner_user_id=OWNER_ID,
        expected_revision=1,
        document=document,
        setup_checksum="c" * 64,
        mechanics_checksum="d" * 64,
        max_revisions=100,
    )

    assert first.revision == 1
    assert second.revision == 2
    assert repository.get(first.setup_id, owner_user_id=OTHER_OWNER_ID) is None
    assert [
        item.revision
        for item in repository.list_revisions(
            first.setup_id,
            owner_user_id=OWNER_ID,
            limit=100,
            offset=0,
        )
    ] == [2, 1]
    summaries = repository.list_setups(owner_user_id=OWNER_ID, limit=100, offset=0)
    assert summaries[0].latest_revision == 2
    assert summaries[0].created_at < summaries[0].updated_at


def test_setup_repository_satisfies_shared_contract() -> None:
    assert_setup_repository_contract(
        InMemorySetupRepository(clock=_Clock()),
        owner_user_id=OWNER_ID,
        other_user_id=OTHER_OWNER_ID,
        document=build_setup_catalog().require_document("standard_6"),
    )


def test_setup_repository_rejects_foreign_and_stale_revision_updates() -> None:
    repository = InMemorySetupRepository()
    document = build_setup_catalog().require_document("standard_6")
    first = repository.create(
        owner_user_id=OWNER_ID,
        display_name="実験設定",
        document=document,
        setup_checksum="a" * 64,
        mechanics_checksum="b" * 64,
        max_setups=100,
    )

    for owner, expected_code in (
        (OTHER_OWNER_ID, ErrorCode.RESOURCE_NOT_FOUND),
        (OWNER_ID, ErrorCode.SETUP_REVISION_CONFLICT),
    ):
        with pytest.raises(AppError) as raised:
            repository.add_revision(
                first.setup_id,
                owner_user_id=owner,
                expected_revision=0,
                document=document,
                setup_checksum="c" * 64,
                mechanics_checksum="d" * 64,
                max_revisions=100,
            )
        assert raised.value.code is expected_code


def test_setup_repository_bounds_owned_list_and_enforces_setup_quota() -> None:
    repository = InMemorySetupRepository(clock=_Clock())
    document = build_setup_catalog().require_document("standard_6")
    created = []
    for index in range(2):
        created.append(
            repository.create(
                owner_user_id=OWNER_ID,
                display_name=f"実験設定{index}",
                document=document,
                setup_checksum="a" * 64,
                mechanics_checksum="b" * 64,
                max_setups=2,
            )
        )

    page = repository.list_setups(owner_user_id=OWNER_ID, limit=1, offset=1)
    assert len(page) == 1
    assert page[0].setup_id in {item.setup_id for item in created}

    with pytest.raises(AppError) as raised:
        repository.create(
            owner_user_id=OWNER_ID,
            display_name="上限超過",
            document=document,
            setup_checksum="a" * 64,
            mechanics_checksum="b" * 64,
            max_setups=2,
        )

    assert raised.value.code is ErrorCode.SETUP_LIMIT_REACHED
