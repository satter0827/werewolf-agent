"""Game event records for replay-oriented logs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from werewolf_agent.commons.security.redaction import redact_mapping
from werewolf_agent.commons.shared.constants import (
    DEFAULT_EVENT_VISIBILITY,
    EVENT_SCHEMA_VERSION,
    GAME_EVENT_FIELD_DAY,
    GAME_EVENT_FIELD_EVENT_TYPE,
    JSON_SEPARATORS,
    MIN_EVENT_DAY,
    PYDANTIC_EXTRA_FORBID,
    PYDANTIC_JSON_MODE,
    EventVisibility,
)
from werewolf_agent.commons.shared.messages import (
    MESSAGE_DAY_MUST_BE_NON_NEGATIVE,
    MESSAGE_EVENT_TYPE_MUST_NOT_BE_BLANK,
)


class GameEvent(BaseModel):
    """A replay-oriented game event written independently from application logs."""

    schema_version: str = EVENT_SCHEMA_VERSION
    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: str
    run_id: str | None = None
    game_id: str | None = None
    phase: str | None = None
    day: int | None = None
    actor_id: str | None = None
    visibility: EventVisibility = DEFAULT_EVENT_VISIBILITY
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra=PYDANTIC_EXTRA_FORBID, frozen=True)

    @field_validator(GAME_EVENT_FIELD_EVENT_TYPE)
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        """Return a non-empty event type."""
        normalized = value.strip()
        if not normalized:
            raise ValueError(MESSAGE_EVENT_TYPE_MUST_NOT_BE_BLANK)
        return normalized

    @field_validator(GAME_EVENT_FIELD_DAY)
    @classmethod
    def validate_day(cls, value: int | None) -> int | None:
        """Return a non-negative day value."""
        if value is not None and value < MIN_EVENT_DAY:
            raise ValueError(MESSAGE_DAY_MUST_BE_NON_NEGATIVE)
        return value

    def to_json_line(self) -> str:
        """Return this event as a single JSON object string."""
        event_record = redact_mapping(self.model_dump(mode=PYDANTIC_JSON_MODE))
        return json.dumps(
            event_record,
            ensure_ascii=False,
            default=str,
            separators=JSON_SEPARATORS,
        )
