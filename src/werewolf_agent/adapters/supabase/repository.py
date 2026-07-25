"""Supabase PostgreSQL implementation of the game repository port."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from werewolf_agent.adapters.supabase.mapping import (
    stored_event,
    stored_game,
    stored_summary,
    stored_turn,
)
from werewolf_agent.adapters.supabase.messages import (
    MESSAGE_WORKER_REQUEST_FAILED,
    message_game_not_found,
)
from werewolf_agent.application.models import (
    GameEventCreate,
    GameRecordCreate,
    GameRecordUpdate,
    StoredGame,
    StoredGameEvent,
    StoredGameSummary,
    StoredGameTurn,
)
from werewolf_agent.application.ports import GameRepository
from werewolf_agent.application.replay import checksum_payload
from werewolf_agent.contracts import GAME_STATUS_COMPLETED, GameStatus


class SupabaseGameRepository(GameRepository):
    """Supabase Postgres implementation of the application repository port."""

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
              definition_snapshot, engine_version, llm_mode, state_checksum,
              created_at, updated_at, completed_at
            )
            values (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s, %s
            )
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
                Jsonb(_json_object(game.config.get("definition_snapshot"))),
                str(game.config.get("engine_version") or "0.1.0"),
                str(game.config.get("llm_mode") or "fake"),
                _state_checksum(game.version, game.private_state, game.public_state),
                now,
                now,
                now if game.status == GAME_STATUS_COMPLETED else None,
            ),
        )
        self._connection.execute(
            """
            insert into private.game_snapshots (
              game_id, config, private_state, pending_actions, checksum, updated_at
            )
            values (%s, %s, %s, %s, %s, %s)
            """,
            (
                game.id,
                Jsonb(game.config),
                Jsonb(game.private_state),
                Jsonb(game.pending_actions),
                checksum_payload(game.private_state),
                now,
            ),
        )
        self._insert_state_version(
            game.id,
            version=game.version,
            private_state=game.private_state,
            public_state=game.public_state,
        )
        self._append_state_event(
            game.id,
            version=game.version,
            phase=game.phase,
            day=game.day,
            private_state=game.private_state,
            public_state=game.public_state,
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
        return stored_game(row) if row is not None else None

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
        return stored_game(row) if row is not None else None

    def list_game_summaries(
        self,
        *,
        status: GameStatus | None,
        limit: int,
        offset: int,
    ) -> list[StoredGameSummary]:
        """Return game summaries."""
        params: list[object] = []
        clauses: list[str] = []
        if self._owner_user_id is not None:
            clauses.append(
                """
                exists (
                  select 1 from public.game_participants participant
                  where participant.game_id = game_summaries.game_id
                    and participant.user_id = %s
                )
                """
            )
            params.append(_uuid_or_none(self._owner_user_id))
        if status is not None:
            clauses.append("status = %s")
            params.append(status)
        where = f"where {' and '.join(clauses)}" if clauses else ""
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
        return [stored_summary(row) for row in rows]

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
                state_checksum = %s,
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
                _state_checksum(update.version, update.private_state, update.public_state),
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
                checksum = %s,
                updated_at = %s
            where game_id = %s
            """,
            (
                Jsonb(update.private_state),
                Jsonb(update.pending_actions),
                checksum_payload(update.private_state),
                now,
                update.id,
            ),
        )
        self._insert_state_version(
            update.id,
            version=update.version,
            private_state=update.private_state,
            public_state=update.public_state,
        )
        self._append_state_event(
            update.id,
            version=update.version,
            phase=update.phase,
            day=update.day,
            private_state=update.private_state,
            public_state=update.public_state,
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
                  game_id, sequence, visibility, phase, day, actor_id, event_type,
                  payload, version, checksum
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    self._current_version(game_id),
                    checksum_payload(event.payload),
                ),
            ).fetchone()
            if row is None:
                raise RuntimeError(MESSAGE_WORKER_REQUEST_FAILED)
            stored = stored_event(row)
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
        return [stored_turn(row) for row in rows]

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

    def replay_records(self, game_id: str) -> Mapping[str, Sequence[Mapping[str, Any]]]:
        """Return private checksum records for administrator replay verification."""
        commands = self._connection.execute(
            """
            select version, command_type, payload, checksum
            from private.accepted_commands
            where game_id = %s
            order by version, accepted_at
            """,
            (game_id,),
        ).fetchall()
        events = self._connection.execute(
            """
            select version, sequence, event_type, payload, checksum
            from private.game_events
            where game_id = %s
            order by sequence
            """,
            (game_id,),
        ).fetchall()
        states = self._connection.execute(
            """
            select version,
                   jsonb_build_object(
                     'version', version,
                     'private_state', private_state,
                     'public_state', public_state
                   ) as payload,
                   checksum
            from private.game_state_versions
            where game_id = %s
            order by version
            """,
            (game_id,),
        ).fetchall()
        return {"commands": commands, "events": events, "states": states}

    def _current_version(self, game_id: UUID) -> int:
        row = self._connection.execute(
            "select version from public.games where game_id = %s",
            (game_id,),
        ).fetchone()
        if row is None:
            raise KeyError(message_game_not_found(game_id))
        return int(row["version"])

    def _insert_state_version(
        self,
        game_id: UUID,
        *,
        version: int,
        private_state: Mapping[str, Any],
        public_state: Mapping[str, Any],
    ) -> None:
        payload = {
            "version": version,
            "private_state": dict(private_state),
            "public_state": dict(public_state),
        }
        self._connection.execute(
            """
            insert into private.game_state_versions (
              game_id, version, private_state, public_state, checksum
            )
            values (%s, %s, %s, %s, %s)
            on conflict (game_id, version) do update set
              private_state = excluded.private_state,
              public_state = excluded.public_state,
              checksum = excluded.checksum
            """,
            (
                game_id,
                version,
                Jsonb(dict(private_state)),
                Jsonb(dict(public_state)),
                checksum_payload(payload),
            ),
        )

    def _append_state_event(
        self,
        game_id: UUID,
        *,
        version: int,
        phase: str,
        day: int,
        private_state: Mapping[str, Any],
        public_state: Mapping[str, Any],
    ) -> None:
        payload = {
            "version": version,
            "private_state": dict(private_state),
            "public_state": dict(public_state),
        }
        self._connection.execute(
            """
            insert into private.game_events (
              game_id, sequence, visibility, phase, day, actor_id,
              event_type, payload, version, checksum
            )
            select %s, coalesce(max(sequence), 0) + 1, 'private', %s, %s, null,
                   'state_committed', %s, %s, %s
            from private.game_events
            where game_id = %s
            """,
            (
                game_id,
                phase,
                day,
                Jsonb(payload),
                version,
                checksum_payload(payload),
                game_id,
            ),
        )


class SupabaseDatabaseUnavailableError(RuntimeError):
    """Indicate that a worker database connection cannot be established."""


def connect_worker_database(dsn: str) -> psycopg.Connection[Any]:
    """Open a worker DB connection with dict rows."""
    try:
        return psycopg.connect(dsn, row_factory=dict_row)
    except psycopg.OperationalError:
        # Do not propagate a driver exception which may include connection
        # details across the adapter boundary.
        raise SupabaseDatabaseUnavailableError from None


def _state_text(state: Mapping[str, Any], key: str) -> str | None:
    value = state.get(key)
    return str(value) if value is not None else None


def _json_object(payload: Any) -> dict[str, Any]:
    return dict(payload) if isinstance(payload, dict) else {}


def _uuid_or_none(value: str | None) -> UUID | None:
    return UUID(value) if value else None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _state_checksum(
    version: int,
    private_state: Mapping[str, Any],
    public_state: Mapping[str, Any],
) -> str:
    return checksum_payload(
        {
            "version": version,
            "private_state": dict(private_state),
            "public_state": dict(public_state),
        }
    )
