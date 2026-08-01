"""外部repository実装へ適用できるapplication契約テストを提供する."""

from __future__ import annotations

from uuid import UUID

from werewolf_agent.application.models import GameEventCreate, GameRecordCreate, GameRecordUpdate
from werewolf_agent.application.ports import GameRepository, SetupRepository
from werewolf_agent.setup import GameSetupDocument


def assert_game_repository_contract(repository: GameRepository, *, game_id: UUID) -> None:
    """隔離した検証用repositoryの保存、timeline、transactionを検証する."""
    created = repository.create(
        GameRecordCreate(
            id=game_id,
            status="running",
            phase="night",
            day=1,
            seed=42,
            config={"llm_mode": "fake"},
            public_state={"players": [{"id": "p1"}, {"id": "p2"}], "summary": {"alive_count": 2}},
            private_state={"secret": ["werewolf"]},
            pending_actions={},
            version=1,
        )
    )
    _require(repository.get(game_id) == created, "created game must be readable")
    _require(repository.get_for_update(game_id) == created, "created game must lock and read")
    updated = repository.save(
        GameRecordUpdate(
            id=game_id,
            status="running",
            phase="day_discussion",
            day=2,
            public_state={"players": [{"id": "p1"}, {"id": "p2"}], "summary": {"alive_count": 1}},
            private_state={"secret": ["werewolf", "seer"]},
            pending_actions={"p1": {"type": "speech"}},
            version=2,
        )
    )
    _require(updated.version == 2, "save must preserve the requested version")
    _require(updated.seed == created.seed, "save must preserve seed")
    _require(updated.config == created.config, "save must preserve config")
    _require(updated.created_at == created.created_at, "save must preserve created_at")
    _require(updated.updated_at.tzinfo is not None, "updated_at must be timezone-aware")
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
    _require(events[1].sequence == events[0].sequence + 1, "event sequence must be contiguous")
    _require(
        repository.latest_public_turn_sequence(game_id) == 1,
        "only public events must advance the public turn sequence",
    )
    turns = repository.list_public_turns(game_id, after=0, limit=10)
    _require(len(turns) == 1, "public timeline must exclude non-public events")
    _require(turns[0].sequence == 1, "public turn sequence must start at 1")
    _require(turns[0].event_sequence == events[1].sequence, "turn must reference its event")
    _require(turns[0].version == 2, "turn must retain the game version")
    _require(turns[0].payload == {"message": "hello"}, "turn must retain public payload")
    _require(
        repository.list_public_turns(game_id, after=1, limit=10) == [],
        "timeline cursor must exclude already consumed turns",
    )
    probe = RuntimeError("rollback probe")
    try:
        with repository.transaction():
            repository.save(
                GameRecordUpdate(
                    id=game_id,
                    status="completed",
                    phase="finished",
                    day=2,
                    public_state={
                        "players": [{"id": "p1"}, {"id": "p2"}],
                        "summary": {"alive_count": 1},
                        "winner": "village",
                    },
                    private_state={"secret": ["changed"]},
                    pending_actions={},
                    version=3,
                )
            )
            repository.append_events(
                game_id,
                [
                    GameEventCreate(
                        visibility="public",
                        phase="finished",
                        day=2,
                        event_type="game_finished",
                        payload={"winner": "village"},
                    )
                ],
            )
            raise probe
    except RuntimeError as error:
        _require(error is probe, "transaction must propagate the original failure")
    else:
        raise AssertionError("transaction must propagate the original failure")
    _require(repository.get(game_id) == updated, "transaction must roll back game changes")
    _require(
        repository.latest_public_turn_sequence(game_id) == 1,
        "transaction must roll back appended events",
    )


def assert_setup_repository_contract(
    repository: SetupRepository,
    *,
    owner_user_id: str,
    other_user_id: str,
    document: GameSetupDocument,
) -> None:
    """Owner分離とimmutable revisionの共通契約を検証する."""
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
    _require(first.revision == 1, "first setup revision must be 1")
    _require(second.revision == 2, "added setup revision must increment")
    _require(
        repository.get(first.setup_id, owner_user_id=other_user_id) is None,
        "setup must be isolated by owner",
    )
    _require(
        repository.get(first.setup_id, owner_user_id=owner_user_id, revision=1) == first,
        "older setup revisions must remain immutable and readable",
    )
    revisions = repository.list_revisions(first.setup_id, owner_user_id=owner_user_id)
    _require(
        [item.revision for item in revisions] == [2, 1],
        "setup revisions must be ordered newest first",
    )
    summaries = repository.list_setups(owner_user_id=owner_user_id)
    _require(len(summaries) == 1, "owner must see one setup summary")
    _require(summaries[0].latest_revision == 2, "summary must expose the latest revision")
    _require(
        summaries[0].created_at <= summaries[0].updated_at,
        "setup timestamps must be ordered",
    )
    _require(
        repository.list_setups(owner_user_id=other_user_id) == [],
        "other owners must not list the setup",
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


__all__ = ["assert_game_repository_contract", "assert_setup_repository_contract"]
