import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from werewolf_agent.contracts import GameError
from werewolf_agent.domain.game.models import Action, Observation
from werewolf_agent.usecase.jobs import (
    AdvanceGameCommand,
    CreateGameCommand,
    GameEventCreate,
    GameNotFoundError,
    GameRepository,
    GameRunCreate,
    GameRunUpdate,
    GameStatus,
    GameUseCaseConfig,
    GameUseCaseDependencies,
    GetGameQuery,
    InvalidGameIdError,
    ListGamesQuery,
    ListGameTurnsQuery,
    ListPublicEventsQuery,
    StoredGameEvent,
    StoredGameRun,
    StoredGameRunSummary,
    StoredGameTurn,
    advance_game,
    create_game,
    get_default_ruleset,
    get_game,
    list_game_turns,
    list_games,
    list_public_events,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class PassingAgent:
    def act(self, observation: Observation) -> Action:
        return Action.pass_(observation.me.id)


class RecordingAgentFactory:
    def __init__(self) -> None:
        self.player_ids: list[str] = []

    def create(self, player_id: str, *, seed: int) -> PassingAgent:
        _ = seed
        self.player_ids.append(player_id)
        return PassingAgent()


class InMemoryGameRepository(GameRepository):
    def __init__(self) -> None:
        self.runs: dict[UUID, StoredGameRun] = {}
        self.events: dict[UUID, list[StoredGameEvent]] = {}
        self.turns: dict[UUID, list[StoredGameTurn]] = {}

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
        self.turns[stored.id] = []
        return stored

    def get(self, game_id: UUID) -> StoredGameRun | None:
        return self.runs.get(game_id)

    def get_for_update(self, game_id: UUID) -> StoredGameRun | None:
        return self.get(game_id)

    def list_run_summaries(
        self,
        *,
        status: GameStatus | None,
        limit: int,
        offset: int,
    ) -> list[StoredGameRunSummary]:
        runs = [
            run
            for run in sorted(self.runs.values(), key=lambda item: item.created_at, reverse=True)
            if status is None or run.status == status
        ]
        return [self._summary(run) for run in runs[offset : offset + limit]]

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
        turn_stream = self.turns.setdefault(run_id, [])
        run = self.runs[run_id]
        turn_stream.extend(
            StoredGameTurn(
                sequence=len(turn_stream) + offset,
                event_sequence=event.sequence,
                version=run.version,
                phase=event.phase,
                day=event.day,
                actor_id=event.actor_id,
                event_type=event.event_type,
                payload=event.payload,
                occurred_at=event.occurred_at,
            )
            for offset, event in enumerate(records, start=1)
            if event.visibility == "public"
        )
        return records

    def list_public_events(
        self,
        run_id: UUID,
        *,
        after: int,
        limit: int,
    ) -> list[StoredGameEvent]:
        return [
            event
            for event in self.events.get(run_id, [])
            if event.visibility == "public" and event.sequence > after
        ][:limit]

    def list_public_turns(
        self,
        run_id: UUID,
        *,
        after: int,
        limit: int,
    ) -> list[StoredGameTurn]:
        return [turn for turn in self.turns.get(run_id, []) if turn.sequence > after][:limit]

    def _summary(self, run: StoredGameRun) -> StoredGameRunSummary:
        state = run.public_state
        summary = state.get("summary") or {}
        return StoredGameRunSummary(
            game_id=run.id,
            status=run.status,
            phase=run.phase,
            day=run.day,
            version=run.version,
            seed=run.seed,
            player_count=len(state.get("players") or []),
            alive_count=int(summary.get("alive_count") or 0),
            winner=state.get("winner"),
            step_count=max(run.version - 1, 0),
            turn_count=len(self.turns.get(run.id, [])),
            created_at=run.created_at,
            updated_at=run.updated_at,
            completed_at=run.updated_at if run.status == "completed" else None,
        )


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
        {"id": " p1 ", "name": "Alice", "agent_type": "llm"},
        {"id": "p2", "name": "Bob", "agent_type": "llm"},
        {"id": "p3", "name": "Carol", "agent_type": "llm"},
        {"id": "p4", "name": "Dave", "agent_type": "llm"},
        {"id": "p5", "name": "Eve", "agent_type": "llm"},
    ]


def test_default_ruleset_returns_business_identifiers_only() -> None:
    result = get_default_ruleset(
        config=GameUseCaseConfig(
            min_players=4,
            max_players=10,
            supported_agent_type="llm",
            default_ruleset_id="custom",
        )
    )

    assert result.id == "custom"
    assert result.player_count == {"min": 4, "max": 10}
    assert result.roles == ["villager", "werewolf", "seer", "knight"]
    assert result.agent_types == ["llm", "human"]


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
            CreateGameCommand(player_count=5, agent={"type": "dummy"}),
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


def test_list_games_and_turns_return_public_read_models() -> None:
    deps, _repository = dependencies()
    created = create_game(CreateGameCommand(player_count=5, seed=1), dependencies=deps)
    advance_game(AdvanceGameCommand(game_id=created.game_id), dependencies=deps)

    runs = list_games(ListGamesQuery(limit=10), dependencies=deps)
    turns = list_game_turns(ListGameTurnsQuery(game_id=created.game_id), dependencies=deps)

    assert runs.runs[0]["game_id"] == created.game_id
    assert runs.runs[0]["turn_count"] == len(turns.turns)
    assert turns.turns
    assert "role_counts" not in json.dumps(turns.model_dump(mode="json"))


def test_advance_game_uses_injected_agent_factory() -> None:
    repository = InMemoryGameRepository()
    factory = RecordingAgentFactory()
    deps = GameUseCaseDependencies(repository=repository, agent_factory=factory)
    created = create_game(CreateGameCommand(player_count=5, seed=1), dependencies=deps)

    advance_game(AdvanceGameCommand(game_id=created.game_id), dependencies=deps)

    assert factory.player_ids == [f"player-{index}" for index in range(1, 6)]
