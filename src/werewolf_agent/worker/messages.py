"""worker messagesが所有する文言."""

from __future__ import annotations

MESSAGE_SUPABASE_WORKER_DSN_REQUIRED = (
    "WEREWOLF_SUPABASE_WORKER_DB_DSN is required for the Supabase queue worker. "
    "Create .env from local Supabase values before starting the worker."
)

MESSAGE_GAME_PARTICIPATION_REQUIRED = "The current user no longer has access to this game."

MESSAGE_PAID_LLM_REQUIRES_MEMBER = "Paid LLM access requires a signed-in user."

MESSAGE_PLAYER_SEAT_NOT_OWNED = "The current user does not own this player seat."

MESSAGE_WORKER_REQUEST_FAILED = "Worker request failed."


def message_error_line(detail: str, suffix: str = "") -> str:
    """Return one CLI error line."""
    return f"Error: {detail}{suffix}"


def message_unsupported_operation_type(operation_type: str) -> str:
    """Return an unsupported Supabase queue operation message."""
    return f"Unsupported operation_type: {operation_type}"
