"""Postgres repository for Supabase worker game jobs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from werewolf_agent.commons.shared.messages import (
    MESSAGE_WORKER_REQUEST_FAILED,
    message_game_not_found,
)
from werewolf_agent.contracts import GAME_STATUS_COMPLETED, GameStatus
from werewolf_agent.usecase.jobs import (
    GameEventCreate,
    GameRecordCreate,
    GameRecordUpdate,
    GameRepository,
    StoredGame,
    StoredGameEvent,
    StoredGameSummary,
    StoredGameTurn,
)


class SupabaseGameRepository(GameRepository):
    """Supabase Postgres implementation of the use case repository port."""

    def __init__(
        self,
        connection: psycopg.Connection[Any],
        *,
        owner_user_id: str | None = None,
    ) -> None:
        """Create a repository bound to one worker transaction."""
        self._connection = connection
        self._owner_user_id = owner_user_id

    def create(self, game: GameRecordCreate) -> StoredGame:
        """Persist a new game and private snapshot."""
        now = _utc_now()
        self._connection.execute(
            """
            insert into public.games (
              game_id, owner_user_id, status, phase, day, version, seed,
              scenario_id, scenario_name, narration_mode, public_state,
              created_at, updated_at, completed_at
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                game.id,
                _uuid_or_none(self._owner_user_id),
                game.status,
                game.phase,
                game.day,
                game.version,
                game.seed,
                _state_text(game.public_state, "scenario_id"),
                _state_text(game.public_state, "scenario_name"),
                str(game.public_state.get("narration_mode") or "standard"),
                Jsonb(game.public_state),
                now,
                now,
                now if game.status == GAME_STATUS_COMPLETED else None,
            ),
        )
        self._connection.execute(
            """
            insert into private.game_snapshots (
              game_id, config, private_state, pending_actions, updated_at
            )
            values (%s, %s, %s, %s, %s)
            """,
            (
                game.id,
                Jsonb(game.config),
                Jsonb(game.private_state),
                Jsonb(game.pending_actions),
                now,
            ),
        )
        stored = self.get(game.id)
        if stored is None:
            raise KeyError(message_game_not_found(game.id))
        self._upsert_summary(stored)
        return stored

    def get(self, game_id: UUID) -> StoredGame | None:
        """Return a game if it exists."""
        row = self._connection.execute(
            """
            select
              g.game_id, g.status, g.phase, g.day, g.seed, g.public_state,
              g.version, g.created_at, g.updated_at,
              s.config, s.private_state, s.pending_actions
            from public.games g
            join private.game_snapshots s on s.game_id = g.game_id
            where g.game_id = %s
            """,
            (game_id,),
        ).fetchone()
        return _stored_game(row) if row is not None else None

    def get_for_update(self, game_id: UUID) -> StoredGame | None:
        """Return a game locked for update if it exists."""
        row = self._connection.execute(
            """
            select
              g.game_id, g.status, g.phase, g.day, g.seed, g.public_state,
              g.version, g.created_at, g.updated_at,
              s.config, s.private_state, s.pending_actions
            from public.games g
            join private.game_snapshots s on s.game_id = g.game_id
            where g.game_id = %s
            for update of g, s
            """,
            (game_id,),
        ).fetchone()
        return _stored_game(row) if row is not None else None

    def list_game_summaries(
        self,
        *,
        status: GameStatus | None,
        limit: int,
        offset: int,
    ) -> list[StoredGameSummary]:
        """Return game summaries."""
        params: list[object] = []
        where = ""
        if status is not None:
            where = "where status = %s"
            params.append(status)
        params.extend([limit, offset])
        rows = self._connection.execute(
            f"""
            select *
            from public.game_summaries
            {where}
            order by updated_at desc, created_at desc
            limit %s offset %s
            """,
            params,
        ).fetchall()
        return [_stored_summary(row) for row in rows]

    def save(self, update: GameRecordUpdate) -> StoredGame:
        """Persist mutable game fields."""
        now = _utc_now()
        result = self._connection.execute(
            """
            update public.games
            set status = %s,
                phase = %s,
                day = %s,
                version = %s,
                public_state = %s,
                scenario_id = %s,
                scenario_name = %s,
                narration_mode = %s,
                updated_at = %s,
                completed_at = case when %s = 'completed' then %s else completed_at end
            where game_id = %s
            """,
            (
                update.status,
                update.phase,
                update.day,
                update.version,
                Jsonb(update.public_state),
                _state_text(update.public_state, "scenario_id"),
                _state_text(update.public_state, "scenario_name"),
                str(update.public_state.get("narration_mode") or "standard"),
                now,
                update.status,
                now,
                update.id,
            ),
        )
        if result.rowcount == 0:
            raise KeyError(message_game_not_found(update.id))
        self._connection.execute(
            """
            update private.game_snapshots
            set private_state = %s,
                pending_actions = %s,
                updated_at = %s
            where game_id = %s
            """,
            (Jsonb(update.private_state), Jsonb(update.pending_actions), now, update.id),
        )
        stored = self.get(update.id)
        if stored is None:
            raise KeyError(message_game_not_found(update.id))
        self._upsert_summary(stored)
        return stored

    def append_events(
        self,
        game_id: UUID,
        events: Sequence[GameEventCreate],
    ) -> list[StoredGameEvent]:
        """Append private event stream records and public turn rows."""
        if not events:
            return []
        last_sequence_row = self._connection.execute(
            "select coalesce(max(sequence), 0) from private.game_events where game_id = %s",
            (game_id,),
        ).fetchone()
        if last_sequence_row is None:
            raise RuntimeError(MESSAGE_WORKER_REQUEST_FAILED)
        last_sequence = last_sequence_row["coalesce"]
        stored_events: list[StoredGameEvent] = []
        for offset, event in enumerate(events, start=1):
            row = self._connection.execute(
                """
                insert into private.game_events (
                  game_id, sequence, visibility, phase, day, actor_id, event_type, payload
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                returning *
                """,
                (
                    game_id,
                    int(last_sequence) + offset,
                    event.visibility,
                    event.phase,
                    event.day,
                    event.actor_id,
                    event.event_type,
                    Jsonb(event.payload),
                ),
            ).fetchone()
            if row is None:
                raise RuntimeError(MESSAGE_WORKER_REQUEST_FAILED)
            stored = _stored_event(row)
            stored_events.append(stored)
            if event.visibility == "public":
                self._append_public_turn(game_id, stored)
        game = self.get(game_id)
        if game is not None:
            self._upsert_summary(game)
        return stored_events

    def latest_public_turn_sequence(self, game_id: UUID) -> int:
        """Return the latest public turn sequence."""
        row = self._connection.execute(
            "select coalesce(max(sequence), 0) from public.game_public_turns where game_id = %s",
            (game_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(MESSAGE_WORKER_REQUEST_FAILED)
        return int(row["coalesce"])

    def list_public_turns(
        self,
        game_id: UUID,
        *,
        after: int,
        limit: int,
    ) -> list[StoredGameTurn]:
        """Return public turns after a cursor."""
        rows = self._connection.execute(
            """
            select *
            from public.game_public_turns
            where game_id = %s and sequence > %s
            order by sequence
            limit %s
            """,
            (game_id, after, limit),
        ).fetchall()
        return [_stored_turn(row) for row in rows]

    def _append_public_turn(self, game_id: UUID, event: StoredGameEvent) -> None:
        game = self.get(game_id)
        if game is None:
            return
        last_sequence = self.latest_public_turn_sequence(game_id)
        self._connection.execute(
            """
            insert into public.game_public_turns (
              game_id, sequence, event_sequence, version, phase, day,
              actor_id, event_type, payload, occurred_at
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                game_id,
                last_sequence + 1,
                event.sequence,
                game.version,
                event.phase,
                event.day,
                event.actor_id,
                event.event_type,
                Jsonb(event.payload),
                event.occurred_at,
            ),
        )

    def _upsert_summary(self, game: StoredGame) -> None:
        public_state = _json_object(game.public_state)
        state_summary = _json_object(public_state.get("summary"))
        turn_count = self.latest_public_turn_sequence(game.id)
        self._connection.execute(
            """
            insert into public.game_summaries (
              game_id, owner_user_id, status, phase, day, version, seed,
              player_count, alive_count, winner, step_count, turn_count,
              created_at, updated_at, completed_at
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (game_id) do update set
              status = excluded.status,
              phase = excluded.phase,
              day = excluded.day,
              version = excluded.version,
              seed = excluded.seed,
              player_count = excluded.player_count,
              alive_count = excluded.alive_count,
              winner = excluded.winner,
              step_count = excluded.step_count,
              turn_count = excluded.turn_count,
              updated_at = excluded.updated_at,
              completed_at = excluded.completed_at
            """,
            (
                game.id,
                _uuid_or_none(self._owner_user_id),
                game.status,
                game.phase,
                game.day,
                game.version,
                game.seed,
                len(public_state.get("players") or []),
                int(state_summary.get("alive_count") or 0),
                public_state.get("winner"),
                max(game.version - 1, 0),
                turn_count,
                game.created_at,
                game.updated_at,
                game.updated_at if game.status == GAME_STATUS_COMPLETED else None,
            ),
        )


def connect_worker_database(dsn: str) -> psycopg.Connection[Any]:
    """Open a worker DB connection with dict rows."""
    return psycopg.connect(dsn, row_factory=dict_row)


def _stored_game(row: Mapping[str, Any]) -> StoredGame:
    return StoredGame.model_validate(
        {
            "id": row["game_id"],
            "status": row["status"],
            "phase": row["phase"],
            "day": row["day"],
            "seed": row.get("seed"),
            "config": _json_object(row.get("config")),
            "public_state": _json_object(row.get("public_state")),
            "private_state": _json_object(row.get("private_state")),
            "pending_actions": _json_object(row.get("pending_actions")),
            "version": row["version"],
            "created_at": _ensure_aware(row["created_at"]),
            "updated_at": _ensure_aware(row["updated_at"]),
        }
    )


def _stored_event(row: Mapping[str, Any]) -> StoredGameEvent:
    return StoredGameEvent.model_validate(
        {
            "sequence": row["sequence"],
            "event_id": row["event_id"],
            "visibility": row["visibility"],
            "phase": row.get("phase"),
            "day": row.get("day"),
            "actor_id": row.get("actor_id"),
            "event_type": row["event_type"],
            "payload": _json_object(row.get("payload")),
            "occurred_at": _ensure_aware(row["occurred_at"]),
        }
    )


def _stored_summary(row: Mapping[str, Any]) -> StoredGameSummary:
    return StoredGameSummary.model_validate(
        {
            "game_id": row["game_id"],
            "status": row["status"],
            "phase": row["phase"],
            "day": row["day"],
            "version": row["version"],
            "seed": row.get("seed"),
            "player_count": row["player_count"],
            "alive_count": row["alive_count"],
            "winner": row.get("winner"),
            "step_count": row["step_count"],
            "turn_count": row["turn_count"],
            "created_at": _ensure_aware(row["created_at"]),
            "updated_at": _ensure_aware(row["updated_at"]),
            "completed_at": _ensure_aware(row["completed_at"])
            if row.get("completed_at") is not None
            else None,
        }
    )


def _stored_turn(row: Mapping[str, Any]) -> StoredGameTurn:
    return StoredGameTurn.model_validate(
        {
            "sequence": row["sequence"],
            "event_sequence": row["event_sequence"],
            "version": row["version"],
            "phase": row.get("phase"),
            "day": row.get("day"),
            "actor_id": row.get("actor_id"),
            "event_type": row["event_type"],
            "payload": _json_object(row.get("payload")),
            "occurred_at": _ensure_aware(row["occurred_at"]),
        }
    )


def _state_text(state: Mapping[str, Any], key: str) -> str | None:
    value = state.get(key)
    return str(value) if value is not None else None


def _json_object(payload: Any) -> dict[str, Any]:
    return dict(payload) if isinstance(payload, dict) else {}


def _ensure_aware(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _uuid_or_none(value: str | None) -> UUID | None:
    return UUID(value) if value else None


def _utc_now() -> datetime:
    return datetime.now(UTC)
