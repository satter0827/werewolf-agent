import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from werewolf_agent.contracts import GameError
from werewolf_agent.usecase.jobs import (
    AdvanceGameCommand,
    CreateGameCommand,
    GameEventCreate,
    GameNotFoundError,
    GameRepository,
    GameRunCreate,
    GameRunUpdate,
    GameUseCaseConfig,
    GameUseCaseDependencies,
    GetGameQuery,
    InvalidGameIdError,
    ListPublicEventsQuery,
    StoredGameEvent,
    StoredGameRun,
    advance_game,
    create_game,
    get_default_ruleset,
    get_game,
    list_public_events,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class InMemoryGameRepository(GameRepository):
    def __init__(self) -> None:
        self.runs: dict[UUID, StoredGameRun] = {}
        self.events: dict[UUID, list[StoredGameEvent]] = {}

    def create(self, run: GameRunCreate) -> StoredGameRun:
        stored = StoredGameRun(
            id=run.id,
            status=run.status,
            phase=run.phase,
            day=run.day,
            seed=run.seed,
            config=run.config,
            public_state=run.public_state,
            private_state=run.private_state,
            version=run.version,
            created_at=NOW,
            updated_at=NOW,
        )
        self.runs[stored.id] = stored
        self.events[stored.id] = []
        return stored

    def get(self, game_id: UUID) -> StoredGameRun | None:
        return self.runs.get(game_id)

    def get_for_update(self, game_id: UUID) -> StoredGameRun | None:
        return self.get(game_id)

    def save(self, update: GameRunUpdate) -> StoredGameRun:
        current = self.runs[update.id]
        stored = StoredGameRun(
            id=update.id,
            status=update.status,
            phase=update.phase,
            day=update.day,
            seed=current.seed,
            config=current.config,
            public_state=update.public_state,
            private_state=update.private_state,
            version=update.version,
            created_at=current.created_at,
            updated_at=NOW,
        )
        self.runs[stored.id] = stored
        return stored

    def append_events(
        self,
        run_id: UUID,
        events: Sequence[GameEventCreate],
    ) -> list[StoredGameEvent]:
        stream = self.events.setdefault(run_id, [])
        records = [
            StoredGameEvent(
                sequence=len(stream) + offset,
                event_id=uuid4(),
                visibility=event.visibility,
                phase=event.phase,
                day=event.day,
                actor_id=event.actor_id,
                event_type=event.event_type,
                payload=event.payload,
                occurred_at=NOW,
            )
            for offset, event in enumerate(events, start=1)
        ]
        stream.extend(records)
        return records

    def list_public_events(self, run_id: UUID, *, after: int) -> list[StoredGameEvent]:
        return [
            event
            for event in self.events.get(run_id, [])
            if event.visibility == "public" and event.sequence > after
        ]


def dependencies(
    *,
    config: GameUseCaseConfig | None = None,
) -> tuple[GameUseCaseDependencies, InMemoryGameRepository]:
    repository = InMemoryGameRepository()
    return GameUseCaseDependencies(
        repository=repository,
        config=config or GameUseCaseConfig(),
    ), repository


def explicit_players() -> list[dict[str, str]]:
    return [
        {"id": " p1 ", "name": "Alice", "agent_type": "dummy"},
        {"id": "p2", "name": "Bob", "agent_type": "dummy"},
        {"id": "p3", "name": "Carol", "agent_type": "dummy"},
        {"id": "p4", "name": "Dave", "agent_type": "dummy"},
        {"id": "p5", "name": "Eve", "agent_type": "dummy"},
    ]


def test_default_ruleset_returns_business_identifiers_only() -> None:
    result = get_default_ruleset(
        config=GameUseCaseConfig(
            min_players=4,
            max_players=10,
            supported_agent_type="dummy",
            default_ruleset_id="custom",
        )
    )

    assert result.id == "custom"
    assert result.player_count == {"min": 4, "max": 10}
    assert result.roles == ["villager", "werewolf", "seer", "knight"]
    assert result.agent_types == ["dummy"]


def test_create_game_normalizes_player_ids_and_sanitizes_public_events() -> None:
    deps, repository = dependencies()

    result = create_game(
        CreateGameCommand(players=explicit_players(), seed=42),
        dependencies=deps,
    )

    assert result.state["players"][0]["id"] == "p1"
    assert "role" not in json.dumps(result.model_dump(mode="json"))
    event_stream = repository.events[UUID(result.game_id)]
    assert event_stream[0].event_type == "game_started"
    assert "role_counts" not in event_stream[0].payload


def test_create_game_rejects_duplicate_normalized_player_ids() -> None:
    deps, _repository = dependencies()
    players = explicit_players()
    players[1]["id"] = "p1"

    with pytest.raises(GameError):
        create_game(CreateGameCommand(players=players), dependencies=deps)


def test_create_game_rejects_unsupported_agent_type() -> None:
    deps, _repository = dependencies()

    with pytest.raises(GameError):
        create_game(
            CreateGameCommand(player_count=5, agent={"type": "llm"}),
            dependencies=deps,
        )


def test_game_id_is_parsed_and_validated_inside_usecase() -> None:
    deps, _repository = dependencies()

    with pytest.raises(InvalidGameIdError):
        get_game(GetGameQuery(game_id="not-a-uuid"), dependencies=deps)

    with pytest.raises(GameNotFoundError):
        get_game(GetGameQuery(game_id=str(uuid4())), dependencies=deps)


def test_advance_game_delegates_core_progression_and_returns_public_payloads() -> None:
    deps, repository = dependencies()
    created = create_game(CreateGameCommand(player_count=5, seed=1), dependencies=deps)

    advanced = advance_game(
        AdvanceGameCommand(game_id=created.game_id),
        dependencies=deps,
    )
    events = list_public_events(
        ListPublicEventsQuery(game_id=created.game_id, after=0),
        dependencies=deps,
    )

    assert advanced.state["version"] == 2
    assert all(event["visibility"] == "public" for event in advanced.events)
    assert "role_counts" not in json.dumps(events.model_dump(mode="json"))
    assert events.events
    assert events.next_after <= repository.events[UUID(created.game_id)][-1].sequence
