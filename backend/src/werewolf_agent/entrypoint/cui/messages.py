"""CLI-owned help text and display messages."""

from __future__ import annotations

HELP_APP = "Werewolf Agent development and gameplay commands."
HELP_OUTPUT_FORMAT = "Output format: table, json, or jsonl."
HELP_SEED = "Deterministic seed."
HELP_MANUAL_PLAYER = "Player id controlled by this CLI."
HELP_ROLE_COUNT = "Role count entry, e.g. werewolf=1."
HELP_GAME_ID_INSPECT = "Game id to inspect."
HELP_GAME_ID_ADVANCE = "Game id to advance."
HELP_MAX_STEPS = "Maximum advance steps."
HELP_LOG_JSONL = "Optional public timeline JSONL."
HELP_POLL_INTERVAL_STEPS = "Seconds to wait between advance steps."
HELP_SHOW_TIMELINE = "Print public timeline items."
HELP_AFTER_SEQUENCE = "Start after this timeline sequence."
HELP_LIMIT_PER_POLL = "Maximum items per poll."
HELP_POLL_INTERVAL_FOLLOW = "Seconds to wait between polls when following."
HELP_FOLLOW = "Keep polling for new items."
HELP_TIMELINE_FILE = "Public timeline JSONL."
HELP_GAME_ID_REPLAY = "Game id to replay from the active data source."
HELP_REPLAY_DELAY = "Seconds to wait between items."
HELP_GAME_STATUS_FILTER = "Optional game status filter."
HELP_GAME_LIST_LIMIT = "Maximum games to return."
HELP_GAME_PAGE_OFFSET = "Game page offset."
HELP_EMAIL = "Supabase account email."
HELP_PASSWORD = "Supabase account password."

TABLE_TITLE_API_HEALTH = "Data Source Health"
TABLE_TITLE_GAME_SETUP = "Game Setup"
TABLE_TITLE_GAMES = "Games"
TABLE_TITLE_GAME_TIMELINE = "Game Timeline"
TABLE_TITLE_DOCTOR = "Werewolf Agent Doctor"

COLUMN_FIELD = "Field"
COLUMN_VALUE = "Value"
COLUMN_CHECK = "Check"
COLUMN_GAME = "Game"
COLUMN_STATUS = "Status"
COLUMN_PHASE = "Phase"
COLUMN_DAY = "Day"
COLUMN_WINNER = "Winner"
COLUMN_TURNS = "Turns"
COLUMN_SEQUENCE = "Seq"
COLUMN_EVENT = "Event"
COLUMN_ACTOR = "Actor"
COLUMN_PAYLOAD = "Payload"

ROW_PLAYER_COUNT = "player count"
ROW_ROLES = "roles"
ROW_DEFAULT_ROLE_COUNTS = "default role counts"
ROW_STATUS = "status"
ROW_PHASE = "phase"
ROW_DAY = "day"
ROW_VERSION = "version"
ROW_ALIVE = "alive"
ROW_ELIMINATED = "eliminated"
ROW_WINNER = "winner"
ROW_ROLE = "role"
ROW_AVAILABLE_ACTIONS = "available actions"
ROW_KNOWN_ROLES = "known roles"

EMPTY_VALUE = "-"
PROMPT_SPEECH = "speech"
LABEL_MANUAL_TOKEN = "manual token"
MESSAGE_REPLAY_SOURCE_REQUIRED = "Either --timeline or --game-id is required."
MESSAGE_LOGIN_SUCCEEDED = "Logged in."
MESSAGE_LOGOUT_SUCCEEDED = "Logged out."
MESSAGE_NOT_LOGGED_IN = "Not logged in. Demo mode is active."
MESSAGE_SUPABASE_LOGIN_CONFIG_REQUIRED = (
    "WEREWOLF_SUPABASE_URL and WEREWOLF_SUPABASE_PUBLISHABLE_KEY are required for login."
)


def table_title_game(game_id: str) -> str:
    """Return the game-state table title."""
    return f"Game {game_id}"


def table_title_observation(player_id: str) -> str:
    """Return the private-observation table title."""
    return f"Observation {player_id}"


def message_created_game(game_id: str) -> str:
    """Return the CLI created-game notice."""
    return f"Created game [bold]{game_id}[/bold]"


def message_manual_token(player_id: str, token: str) -> str:
    """Return the CLI manual-token notice."""
    return f"[yellow]{LABEL_MANUAL_TOKEN}[/yellow] {player_id}: {token}"


def message_game_completed(*, winner: str, steps: int) -> str:
    """Return the CLI game-completed notice."""
    return f"[bold green]Game completed[/bold green]: winner={winner}, steps={steps}"


def message_timeline_item(*, sequence: int, event_type: str, payload: object) -> str:
    """Return one rich-formatted timeline item line."""
    return f"[dim]{sequence}[/dim] [bold]{event_type}[/bold] {payload}"


def message_next_offset(next_offset: int) -> str:
    """Return the next page offset notice."""
    return f"[dim]next offset: {next_offset}[/dim]"


def message_target_prompt(action_type: str) -> str:
    """Return the target prompt for an action type."""
    return f"{action_type} target_id"
