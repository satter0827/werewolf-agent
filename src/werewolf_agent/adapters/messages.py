"""adapters messagesが所有する文言."""

from __future__ import annotations

MESSAGE_SUPABASE_CLIENT_CONFIG_REQUIRED = (
    "WEREWOLF_SUPABASE_URL and WEREWOLF_SUPABASE_PUBLISHABLE_KEY are required. "
    "Create .env from local Supabase values before starting CLI or Streamlit."
)


def message_definition_settings_invalid(error: object) -> str:
    """Definition resourceの検証失敗を返す."""
    return f"definition settings are invalid: {error}"


def message_role_definition_missing_player_counts(missing: str) -> str:
    """Role count定義の不足を返す."""
    return (
        f"game role definition default_role_counts must define configured player counts: {missing}"
    )


def message_unknown_setup_preset(preset_id: str) -> str:
    """未知のsetup presetを返す."""
    return f"Unknown setup preset: {preset_id}"
