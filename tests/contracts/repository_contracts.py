"""Game/Setup repository実装へ共通適用する振る舞い契約。"""

from __future__ import annotations

from uuid import UUID

from werewolf_agent.application.models import GameEventCreate, GameRecordCreate, GameRecordUpdate
from werewolf_agent.application.ports import GameRepository, SetupRepository
from werewolf_agent.setup import GameSetupDocument


def assert_game_repository_contract(
    repository: GameRepository,
    *,
    game_id: UUID,
) -> None:
    """保存、更新、event sequence、公開timelineの共通契約を検証する。"""
    created = repository.create(
        GameRecordCreate(
            id=game_id,
            status="running",
            phase="night",
            day=1,
            seed=42,
            config={"llm_mode": "fake"},
            public_state={
                "players": [{"id": "p1"}, {"id": "p2"}],
                "summary": {"alive_count": 2},
            },
            private_state={"secret": ["werewolf"]},
            pending_actions={},
            version=1,
        )
    )
    loaded = repository.get(game_id)
    assert loaded == created
    assert repository.get_for_update(game_id) == created

    updated = repository.save(
        GameRecordUpdate(
            id=game_id,
            status="running",
            phase="day_discussion",
            day=2,
            public_state={
                "players": [{"id": "p1"}, {"id": "p2"}],
                "summary": {"alive_count": 1},
            },
            private_state={"secret": ["werewolf", "seer"]},
            pending_actions={"p1": {"type": "speech"}},
            version=2,
        )
    )
    assert updated.version == 2
    assert updated.seed == created.seed
    assert updated.config == created.config
    assert updated.created_at == created.created_at
    assert updated.updated_at.tzinfo is not None

    events = repository.append_events(
        game_id,
        [
            GameEventCreate(visibility="debug", event_type="private", payload={"x": 1}),
            GameEventCreate(
                visibility="public",
                phase="day_discussion",
                day=2,
                actor_id="p1",
                event_type="speech",
                payload={"message": "hello"},
            ),
        ],
    )
    assert events[1].sequence == events[0].sequence + 1
    assert repository.latest_public_turn_sequence(game_id) == 1
    turns = repository.list_public_turns(game_id, after=0, limit=10)
    assert len(turns) == 1
    assert turns[0].sequence == 1
    assert turns[0].event_sequence == events[1].sequence
    assert turns[0].version == 2
    assert turns[0].payload == {"message": "hello"}
    assert repository.list_public_turns(game_id, after=1, limit=10) == []


def assert_setup_repository_contract(
    repository: SetupRepository,
    *,
    owner_user_id: str,
    other_user_id: str,
    document: GameSetupDocument,
) -> None:
    """Owner分離とimmutable revisionの共通契約を検証する。"""
    first = repository.create(
        owner_user_id=owner_user_id,
        display_name="実験設定",
        document=document,
        setup_checksum="a" * 64,
        mechanics_checksum="b" * 64,
    )
    second = repository.add_revision(
        first.setup_id,
        owner_user_id=owner_user_id,
        expected_revision=1,
        document=document,
        setup_checksum="c" * 64,
        mechanics_checksum="d" * 64,
    )

    assert first.revision == 1
    assert second.revision == 2
    assert repository.get(first.setup_id, owner_user_id=other_user_id) is None
    assert repository.get(first.setup_id, owner_user_id=owner_user_id, revision=1) == first
    assert [
        item.revision
        for item in repository.list_revisions(first.setup_id, owner_user_id=owner_user_id)
    ] == [2, 1]
    summaries = repository.list_setups(owner_user_id=owner_user_id)
    assert len(summaries) == 1
    assert summaries[0].latest_revision == 2
    assert summaries[0].created_at <= summaries[0].updated_at
    assert repository.list_setups(owner_user_id=other_user_id) == []
