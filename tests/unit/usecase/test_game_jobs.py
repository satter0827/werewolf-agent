import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from werewolf_agent.contracts import GameError, GameNotFoundError, InvalidGameIdError
from werewolf_agent.usecase.jobs import (
    AdvanceGameRunCommand,
    CreateGameRunCommand,
    GameEventCreate,
    GameRepository,
    GameRunCreate,
    GameRunUpdate,
    GameStatus,
    GameUseCaseConfig,
    GameUseCaseDependencies,
    GameUseCases,
    GetGameRunQuery,
    GetGameTimelineQuery,
    ListGameRunsQuery,
    NullTelemetrySink,
    PlayerActionCommand,
    StoredGameEvent,
    StoredGameRun,
    StoredGameRunSummary,
    StoredGameTurn,
    TelemetryEvent,
    TelemetrySink,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_null_telemetry_sink_accepts_events() -> None:
    NullTelemetrySink().record(TelemetryEvent("game.phase.advance_started"))


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
            pending_actions=run.pending_actions,
            control_token_hashes=run.control_token_hashes,
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
            pending_actions=update.pending_actions,
            control_token_hashes=current.control_token_hashes,
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

    def latest_public_turn_sequence(self, run_id: UUID) -> int:
        turns = self.turns.get(run_id, [])
        return turns[-1].sequence if turns else 0

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


class CollectingTelemetrySink:
    def __init__(self) -> None:
        self.events: list[TelemetryEvent] = []

    def record(self, event: TelemetryEvent) -> None:
        self.events.append(event)


def dependencies(
    *,
    config: GameUseCaseConfig | None = None,
    telemetry: TelemetrySink | None = None,
) -> tuple[GameUseCaseDependencies, InMemoryGameRepository]:
    repository = InMemoryGameRepository()
    return GameUseCaseDependencies(
        repository=repository,
        config=config or GameUseCaseConfig(),
        telemetry=telemetry or CollectingTelemetrySink(),
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
    deps, _repository = dependencies(
        config=GameUseCaseConfig(
            min_players=4,
            max_players=10,
            supported_agent_type="llm",
            default_ruleset_id="custom",
        )
    )
    result = GameUseCases(deps).get_default_ruleset()

    assert result.id == "custom"
    assert result.player_count == {"min": 4, "max": 10}
    assert result.roles == ["villager", "werewolf", "seer", "knight"]
    assert result.agent_types == ["llm", "human"]


def test_create_game_normalizes_player_ids_and_sanitizes_public_events() -> None:
    deps, repository = dependencies()

    result = GameUseCases(deps).create_game_run(
        CreateGameRunCommand(players=explicit_players(), seed=42),
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
        GameUseCases(deps).create_game_run(CreateGameRunCommand(players=players))


def test_create_game_rejects_unsupported_agent_type() -> None:
    deps, _repository = dependencies()

    with pytest.raises(GameError):
        GameUseCases(deps).create_game_run(
            CreateGameRunCommand(player_count=5, agent={"type": "dummy"})
        )


def test_game_id_is_parsed_and_validated_inside_usecase() -> None:
    deps, _repository = dependencies()

    with pytest.raises(InvalidGameIdError):
        GameUseCases(deps).get_game_run(GetGameRunQuery(game_id="not-a-uuid"))

    with pytest.raises(GameNotFoundError):
        GameUseCases(deps).get_game_run(GetGameRunQuery(game_id=str(uuid4())))


def test_advance_game_delegates_core_progression_and_returns_public_payloads() -> None:
    telemetry = CollectingTelemetrySink()
    deps, repository = dependencies(telemetry=telemetry)
    use_cases = GameUseCases(deps)
    created = use_cases.create_game_run(CreateGameRunCommand(player_count=5, seed=1))

    advanced = use_cases.advance_game_run(AdvanceGameRunCommand(game_id=created.game_id))
    timeline = use_cases.get_game_timeline(GetGameTimelineQuery(game_id=created.game_id, after=0))

    assert advanced.state["version"] == 2
    assert advanced.timeline
    assert "role_counts" not in json.dumps(timeline.model_dump(mode="json"))
    assert timeline.items
    assert timeline.next_after <= repository.latest_public_turn_sequence(UUID(created.game_id))
    assert "game.phase.drive_started" in [event.action for event in telemetry.events]
    assert "game.phase.advance_completed" in [event.action for event in telemetry.events]
    assert all("private_state" not in event.fields for event in telemetry.events)
    agent_events = [
        event for event in telemetry.events if event.action == "game.agent_action.generated"
    ]
    assert agent_events
    assert all("player_id" not in event.fields for event in agent_events)
    assert all("game_action_type" not in event.fields for event in agent_events)
    assert all("agent_type" in event.fields for event in agent_events)


def test_submit_manual_action_emits_sanitized_telemetry() -> None:
    telemetry = CollectingTelemetrySink()
    deps, _repository = dependencies(telemetry=telemetry)
    use_cases = GameUseCases(deps)
    created = use_cases.create_game_run(
        CreateGameRunCommand(
            players=[
                {"id": "p1", "name": "Alice", "agent_type": "human"},
                {"id": "p2", "name": "Bob", "agent_type": "llm"},
                {"id": "p3", "name": "Carol", "agent_type": "llm"},
                {"id": "p4", "name": "Dave", "agent_type": "llm"},
                {"id": "p5", "name": "Eve", "agent_type": "llm"},
            ],
            seed=1,
        ),
    )
    use_cases.advance_game_run(AdvanceGameRunCommand(game_id=created.game_id))

    use_cases.submit_player_action(
        PlayerActionCommand(
            game_id=created.game_id,
            player_id="p1",
            control_token=created.control_tokens["p1"] if created.control_tokens else "",
            type="speech",
            message="hello",
        )
    )

    event = next(
        event for event in telemetry.events if event.action == "game.manual_action.accepted"
    )
    assert event.fields["has_message"] is True
    assert "player_id" not in event.fields
    assert "game_action_type" not in event.fields
    assert "control_token" not in event.fields
    assert "message" not in event.fields


def test_list_games_and_turns_return_public_read_models() -> None:
    deps, _repository = dependencies()
    use_cases = GameUseCases(deps)
    created = use_cases.create_game_run(CreateGameRunCommand(player_count=5, seed=1))
    use_cases.advance_game_run(AdvanceGameRunCommand(game_id=created.game_id))

    runs = use_cases.list_game_runs(ListGameRunsQuery(limit=10))
    timeline = use_cases.get_game_timeline(GetGameTimelineQuery(game_id=created.game_id))

    assert runs.runs[0]["game_id"] == created.game_id
    assert runs.runs[0]["turn_count"] == len(timeline.items)
    assert timeline.items
    assert "role_counts" not in json.dumps(timeline.model_dump(mode="json"))
