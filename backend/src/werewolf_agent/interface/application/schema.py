"""Database schema constants for ORM models and Alembic migrations."""

from __future__ import annotations

from typing import Final

from werewolf_agent.commons.shared.constants import EVENT_VISIBILITY_PUBLIC

GAMES_TABLE: Final = "games"
GAME_EVENTS_TABLE: Final = "game_events"
GAME_SUMMARIES_TABLE: Final = "game_summaries"
GAME_TURNS_TABLE: Final = "game_turns"

ID_COLUMN: Final = "id"
GAME_ID_COLUMN: Final = "game_id"
STATUS_COLUMN: Final = "status"
PHASE_COLUMN: Final = "phase"
DAY_COLUMN: Final = "day"
SEED_COLUMN: Final = "seed"
CONFIG_COLUMN: Final = "config"
PUBLIC_STATE_COLUMN: Final = "public_state"
PRIVATE_STATE_COLUMN: Final = "private_state"
PENDING_ACTIONS_COLUMN: Final = "pending_actions"
MANUAL_TOKEN_HASHES_COLUMN: Final = "manual_token_hashes"
VERSION_COLUMN: Final = "version"
CREATED_AT_COLUMN: Final = "created_at"
UPDATED_AT_COLUMN: Final = "updated_at"
SEQUENCE_COLUMN: Final = "sequence"
EVENT_SEQUENCE_COLUMN: Final = "event_sequence"
EVENT_ID_COLUMN: Final = "event_id"
VISIBILITY_COLUMN: Final = "visibility"
ACTOR_ID_COLUMN: Final = "actor_id"
EVENT_TYPE_COLUMN: Final = "event_type"
PAYLOAD_COLUMN: Final = "payload"
OCCURRED_AT_COLUMN: Final = "occurred_at"
PLAYER_COUNT_COLUMN: Final = "player_count"
ALIVE_COUNT_COLUMN: Final = "alive_count"
WINNER_COLUMN: Final = "winner"
STEP_COUNT_COLUMN: Final = "step_count"
TURN_COUNT_COLUMN: Final = "turn_count"
COMPLETED_AT_COLUMN: Final = "completed_at"

GAMES_ID_REFERENCE: Final = f"{GAMES_TABLE}.{ID_COLUMN}"

UUID_TEXT_LENGTH: Final = 36
STATUS_TEXT_LENGTH: Final = 24
PHASE_TEXT_LENGTH: Final = 32
ACTOR_ID_TEXT_LENGTH: Final = 128
EVENT_TYPE_TEXT_LENGTH: Final = 64
WINNER_TEXT_LENGTH: Final = STATUS_TEXT_LENGTH

DEFAULT_EVENT_VISIBILITY: Final = EVENT_VISIBILITY_PUBLIC
INITIAL_GAME_DAY: Final = 1
INITIAL_GAME_VERSION: Final = 1
EMPTY_COUNT_DEFAULT: Final = 0
EMPTY_JSON_OBJECT_SQL: Final = "'{}'"

GAME_EVENTS_GAME_SEQUENCE_UNIQUE: Final = "game_events_game_sequence_unique"
GAME_TURNS_GAME_SEQUENCE_UNIQUE: Final = "game_turns_game_sequence_unique"
GAME_TURNS_GAME_EVENT_UNIQUE: Final = "game_turns_game_event_unique"
