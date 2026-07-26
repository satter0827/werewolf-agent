"""adapters supabase messagesが所有する文言."""

from __future__ import annotations

MESSAGE_GAME_NOT_FOUND_TEMPLATE = "Game not found: {game_id}"

MESSAGE_SUPABASE_AUTH_UNAVAILABLE = "Supabase Auth is unavailable."

MESSAGE_SUPABASE_AUTH_INCOMPLETE_SESSION = "Supabase Auth returned an incomplete session."

MESSAGE_WORKER_REQUEST_FAILED = "Worker request failed."


def message_game_not_found(game_id: object) -> str:
    """Return an internal persistence missing-row message."""
    return MESSAGE_GAME_NOT_FOUND_TEMPLATE.format(game_id=game_id)
