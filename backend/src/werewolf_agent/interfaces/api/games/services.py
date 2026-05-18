"""Application-facing persistence services for the games API."""

from __future__ import annotations

import random
import uuid
from collections import Counter
from collections.abc import Sequence
from typing import Any

from django.db import transaction
from django.db.models import Max
from rest_framework.exceptions import NotFound

from werewolf_agent.agents.fake_llm import FakeLlmAgent
from werewolf_agent.commons import GameError, GamePhaseError
from werewolf_agent.domain import (
    AgentAction,
    DomainEvent,
    Faction,
    Game,
    GameConfig,
    GameSnapshot,
    NightAction,
    PassAction,
    Phase,
    PlayerConfig,
    PlayerStatus,
    Role,
    SpeechAction,
    TieBreakPolicy,
    VoteAction,
)
from werewolf_agent.interfaces.api.games.models import GameEventRecord, GameRun
from werewolf_agent.interfaces.api.games.schemas import (
    CreateGamePlayer,
    CreateGameRequest,
    GameEventsResponse,
    GameResponse,
    PublicGameEvent,
    PublicGameState,
    PublicPlayerState,
    RulesetResponse,
    StepGameResponse,
)

MIN_PLAYERS = 5
MAX_PLAYERS = 8
SUPPORTED_AGENT_TYPE = "dummy"


class _EventCollector:
    """In-memory domain event sink used before records are persisted."""

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def write(self, event: DomainEvent) -> None:
        """Collect one domain event."""
        self.events.append(event)


def default_ruleset() -> RulesetResponse:
    """Return the public MVP ruleset metadata."""
    return RulesetResponse(
        id="default",
        name="MVP Default",
        description="5〜8人向けの最小同期 API ルールセットです。",
        player_count={"min": MIN_PLAYERS, "max": MAX_PLAYERS},
        roles=[
            {"id": "villager", "name": "村人"},
            {"id": "werewolf", "name": "人狼"},
            {"id": "seer", "name": "占い師"},
            {"id": "knight", "name": "騎士"},
        ],
        phases=[
            {"id": Phase.NIGHT.value, "name": "夜"},
            {"id": Phase.DAY_DISCUSSION.value, "name": "昼チャット"},
            {"id": Phase.VOTING.value, "name": "投票"},
            {"id": Phase.FINISHED.value, "name": "終了"},
        ],
        agent_types=[{"id": SUPPORTED_AGENT_TYPE, "name": "Dummy Agent"}],
    )


def create_game_run(request: CreateGameRequest) -> GameResponse:
    """Create and persist one deterministic game."""
    game_id = uuid.uuid4()
    _validate_agent_config(request)
    players = _player_configs(request)
    config = _domain_config(request, game_id=str(game_id), player_count=len(players))
    collector = _EventCollector()
    game = Game.start(
        config=config,
        players=players,
        rng=random.Random(request.seed),
        event_sink=collector,
    )
    snapshot = game.snapshot()
    public_state = _public_state_from_snapshot(
        snapshot,
        version=1,
        seed=request.seed,
    )

    with transaction.atomic():
        run = GameRun.objects.create(
            id=game_id,
            status=public_state.status,
            phase=public_state.phase,
            day=public_state.day,
            seed=request.seed,
            config=config.model_dump(mode="json"),
            public_state=public_state.model_dump(mode="json"),
            private_state=snapshot.model_dump(mode="json"),
            version=1,
        )
        _append_events(run, collector.events)

    return GameResponse(game_id=str(run.id), state=_public_state_from_run(run))


def get_game_run(game_id: uuid.UUID) -> GameResponse:
    """Return the current public state for one game run."""
    run = _get_run(game_id)
    return GameResponse(game_id=str(run.id), state=_public_state_from_run(run))


def step_game_run(game_id: uuid.UUID) -> StepGameResponse:
    """Advance one game run by one deterministic API-side step."""
    with transaction.atomic():
        run = _get_run_for_update(game_id)
        if run.status == GameRun.STATUS_COMPLETED:
            raise GamePhaseError("Finished games cannot be advanced.")

        snapshot = GameSnapshot.model_validate(run.private_state)
        collector = _EventCollector()
        game = Game.restore(
            snapshot,
            rng=random.Random(_runtime_seed(run.seed, run.version)),
            event_sink=collector,
        )
        _drive_current_phase(game, seed=run.seed, version=run.version)
        next_snapshot = game.advance_phase()
        next_public_state = _public_state_from_snapshot(
            next_snapshot,
            version=run.version + 1,
            seed=run.seed,
            created_at=run.created_at,
        )

        run.status = next_public_state.status
        run.phase = next_public_state.phase
        run.day = next_public_state.day
        run.public_state = next_public_state.model_dump(mode="json")
        run.private_state = next_snapshot.model_dump(mode="json")
        run.version += 1
        run.save(
            update_fields=[
                "status",
                "phase",
                "day",
                "public_state",
                "private_state",
                "version",
                "updated_at",
            ]
        )
        records = _append_events(run, collector.events)

    return StepGameResponse(
        game_id=str(run.id),
        status=run.status,
        state=_public_state_from_run(run),
        events=[_event_from_record(record) for record in records if _is_public_record(record)],
    )


def list_public_events(game_id: uuid.UUID, *, after: int = 0) -> GameEventsResponse:
    """List public events after a sequence number."""
    run = _get_run(game_id)
    records = list(
        GameEventRecord.objects.filter(
            run=run,
            visibility=GameEventRecord.VISIBILITY_PUBLIC,
            sequence__gt=after,
        ).order_by("sequence")
    )
    next_after = records[-1].sequence if records else after
    return GameEventsResponse(
        game_id=str(run.id),
        events=[_event_from_record(record) for record in records],
        next_after=next_after,
    )


def _player_configs(request: CreateGameRequest) -> list[PlayerConfig]:
    if request.players is not None:
        _validate_players(request.players)
        return [PlayerConfig(player_id=player.id, name=player.name) for player in request.players]

    player_count = request.resolved_player_count
    if player_count < MIN_PLAYERS or player_count > MAX_PLAYERS:
        raise GameError(f"player_count must be between {MIN_PLAYERS} and {MAX_PLAYERS}.")
    return [
        PlayerConfig(player_id=f"player-{index}", name=f"Player {index}")
        for index in range(1, player_count + 1)
    ]


def _validate_players(players: Sequence[CreateGamePlayer]) -> None:
    if len(players) < MIN_PLAYERS or len(players) > MAX_PLAYERS:
        raise GameError(f"player count must be between {MIN_PLAYERS} and {MAX_PLAYERS}.")

    unsupported_agent_types = sorted(
        {player.agent_type for player in players if player.agent_type != SUPPORTED_AGENT_TYPE}
    )
    if unsupported_agent_types:
        raise GameError("Only dummy agent_type is supported for the MVP API.")

    duplicate_ids = sorted(
        player_id
        for player_id, count in Counter(player.id for player in players).items()
        if count > 1
    )
    if duplicate_ids:
        raise GameError("player id values must be unique.")


def _validate_agent_config(request: CreateGameRequest) -> None:
    if request.agent.type != SUPPORTED_AGENT_TYPE:
        raise GameError("Only dummy agent type is supported for the MVP API.")


def _domain_config(
    request: CreateGameRequest,
    *,
    game_id: str,
    player_count: int,
) -> GameConfig:
    rule_config = request.rule_config
    role_counts = _role_counts(player_count, rule_config.role_counts)
    return GameConfig(
        game_id=game_id,
        player_count=player_count,
        role_counts=role_counts,
        seed=request.seed,
        day_speech_turns=rule_config.day_speech_turns,
        tie_break_policy=TieBreakPolicy(rule_config.tie_break_policy),
        allow_self_vote=rule_config.allow_self_vote,
    )


def _role_counts(
    player_count: int,
    requested_counts: dict[str, int] | None,
) -> dict[Role, int]:
    if requested_counts is not None:
        return {Role(role): count for role, count in requested_counts.items()}
    return {
        Role.WEREWOLF: 1,
        Role.SEER: 1,
        Role.KNIGHT: 1,
        Role.VILLAGER: player_count - 3,
    }


def _drive_current_phase(game: Game, *, seed: int | None, version: int) -> None:
    snapshot = game.snapshot()
    turn_count = snapshot.config.day_speech_turns if snapshot.phase is Phase.DAY_DISCUSSION else 1
    for turn in range(turn_count):
        current_snapshot = game.snapshot()
        for index, player in enumerate(current_snapshot.players.values()):
            if player.status is not PlayerStatus.ALIVE:
                continue
            agent = FakeLlmAgent(
                player.player_id,
                rng=random.Random(_agent_seed(seed, version, index, turn)),
            )
            action = agent.act(game.observation_for(player.player_id))
            _submit_agent_action(game, action)


def _submit_agent_action(game: Game, action: AgentAction) -> None:
    if isinstance(action, SpeechAction):
        game.submit_day_action(action)
        return
    if isinstance(action, VoteAction):
        game.submit_vote(action)
        return
    if isinstance(action, NightAction):
        game.submit_night_action(action)
        return
    if isinstance(action, PassAction):
        return
    raise GameError("Unsupported agent action.")


def _get_run(game_id: uuid.UUID) -> GameRun:
    try:
        return GameRun.objects.get(id=game_id)
    except GameRun.DoesNotExist as exc:
        raise NotFound("Game not found.") from exc


def _get_run_for_update(game_id: uuid.UUID) -> GameRun:
    try:
        return GameRun.objects.select_for_update().get(id=game_id)
    except GameRun.DoesNotExist as exc:
        raise NotFound("Game not found.") from exc


def _append_events(run: GameRun, events: list[DomainEvent]) -> list[GameEventRecord]:
    if not events:
        return []

    last_sequence = (
        GameEventRecord.objects.filter(run=run).aggregate(max_sequence=Max("sequence"))[
            "max_sequence"
        ]
        or 0
    )
    records = []
    for offset, event in enumerate(events, start=1):
        records.append(
            GameEventRecord.objects.create(
                run=run,
                sequence=last_sequence + offset,
                visibility=event.visibility.value,
                phase=event.phase.value if event.phase is not None else None,
                day=event.day,
                actor_id=event.actor_id,
                event_type=event.event_type,
                payload=_public_safe_payload(event),
            )
        )
    return records


def _public_state_from_run(run: GameRun) -> PublicGameState:
    payload = dict(run.public_state)
    payload["created_at"] = run.created_at
    payload["updated_at"] = run.updated_at
    return PublicGameState.model_validate(payload)


def _public_state_from_snapshot(
    snapshot: GameSnapshot,
    *,
    version: int,
    seed: int | None,
    created_at: Any | None = None,
) -> PublicGameState:
    players = [
        PublicPlayerState(
            id=player.player_id,
            name=player.name,
            alive=player.status is PlayerStatus.ALIVE,
            status=player.status.value,
            eliminated_day=player.eliminated_day,
            killed_night=player.killed_night,
        )
        for player in snapshot.players.values()
    ]
    alive_player_ids = [
        player.player_id
        for player in snapshot.players.values()
        if player.status is PlayerStatus.ALIVE
    ]
    eliminated_player_ids = [
        player.player_id
        for player in snapshot.players.values()
        if player.status is PlayerStatus.DEAD
    ]
    return PublicGameState(
        game_id=snapshot.game_id,
        status=_status_from_snapshot(snapshot),
        phase=snapshot.phase.value,
        day=snapshot.day,
        version=version,
        seed=seed,
        players=players,
        alive_player_ids=alive_player_ids,
        eliminated_player_ids=eliminated_player_ids,
        winner=_winner_from_snapshot(snapshot),
        summary={
            "alive_count": len(alive_player_ids),
            "eliminated_count": len(eliminated_player_ids),
            "speech_count": len(snapshot.speeches),
            "vote_rounds": len(snapshot.vote_history),
            "night_rounds": len(snapshot.night_history),
        },
        created_at=created_at,
    )


def _event_from_record(record: GameEventRecord) -> PublicGameEvent:
    return PublicGameEvent(
        sequence=record.sequence,
        event_id=record.event_id,
        event_type=record.event_type,
        phase=record.phase,
        day=record.day,
        actor_id=record.actor_id,
        visibility="public",
        payload=_json_payload(record.payload),
        occurred_at=record.occurred_at,
    )


def _status_from_snapshot(snapshot: GameSnapshot) -> str:
    if snapshot.phase is Phase.FINISHED:
        return GameRun.STATUS_COMPLETED
    return GameRun.STATUS_RUNNING


def _winner_from_snapshot(snapshot: GameSnapshot) -> str | None:
    if snapshot.win_result is None:
        return None
    if snapshot.win_result.winner is Faction.VILLAGE:
        return "villagers"
    return "werewolves"


def _is_public_record(record: GameEventRecord) -> bool:
    return record.visibility == GameEventRecord.VISIBILITY_PUBLIC


def _json_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return dict(payload)


def _public_safe_payload(event: DomainEvent) -> dict[str, Any]:
    payload = _json_payload(event.payload)
    if event.event_type == "game_started":
        payload.pop("role_counts", None)
    return payload


def _runtime_seed(seed: int | None, version: int) -> int:
    return (seed or 0) + version * 1009


def _agent_seed(seed: int | None, version: int, index: int, turn: int = 0) -> int:
    return (seed or 0) + version * 1009 + index * 131 + turn * 1709
