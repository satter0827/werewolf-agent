"""CLI-owned help text and display messages."""

from __future__ import annotations

HELP_APP = "Werewolf Agentのゲーム操作と開発診断を行います。"
HELP_OUTPUT_FORMAT = "出力形式をtable、json、jsonlから選びます。"
HELP_SEED = "公開player rosterの再現に使用するシードです。"
HELP_DELIBERATION_LEVEL = "エージェントの思考レベルをquick、standard、deepから選びます。"
HELP_MANUAL_PLAYER = "CLIで操作するプレイヤーIDです。"
HELP_ROLE_COUNT = "役職人数をwerewolf=1の形式で指定します。"
HELP_GAME_ID_INSPECT = "表示するゲームIDです。"
HELP_GAME_ID_ADVANCE = "進行するゲームIDです。"
HELP_MAX_STEPS = "進行する最大ステップ数です。"
HELP_LOG_JSONL = "公開タイムラインを保存するJSONLファイルです。"
HELP_POLL_INTERVAL_STEPS = "進行ステップ間の待機秒数です。"
HELP_SHOW_TIMELINE = "公開タイムラインを表示します。"
HELP_AFTER_SEQUENCE = "この連番より後のタイムラインを取得します。"
HELP_LIMIT_PER_POLL = "1回に取得する最大件数です。"
HELP_POLL_INTERVAL_FOLLOW = "継続取得時の待機秒数です。"
HELP_FOLLOW = "新しい項目を継続して取得します。"
HELP_TIMELINE_FILE = "公開タイムラインのJSONLファイルです。"
HELP_GAME_ID_REPLAY = "APIから再生するゲームIDです。"
HELP_REPLAY_DELAY = "項目を表示する間隔の秒数です。"
HELP_GAME_STATUS_FILTER = "ゲーム状態で絞り込みます。"
HELP_GAME_LIST_LIMIT = "取得するゲームの最大件数です。"
HELP_GAME_PAGE_OFFSET = "ゲーム一覧の開始位置です。"

TABLE_TITLE_API_HEALTH = "接続状態"
TABLE_TITLE_GAME_SETUP = "ゲーム設定"
TABLE_TITLE_GAMES = "ゲーム一覧"
TABLE_TITLE_GAME_TIMELINE = "ゲームタイムライン"
TABLE_TITLE_DOCTOR = "Werewolf Agent 診断"

COLUMN_FIELD = "項目"
COLUMN_VALUE = "値"
COLUMN_CHECK = "確認項目"
COLUMN_GAME = "ゲーム"
COLUMN_STATUS = "状態"
COLUMN_PHASE = "フェーズ"
COLUMN_DAY = "日"
COLUMN_WINNER = "勝利陣営"
COLUMN_TURNS = "ターン"
COLUMN_SEQUENCE = "連番"
COLUMN_EVENT = "イベント"
COLUMN_ACTOR = "実行者"
COLUMN_PAYLOAD = "内容"

ROW_PLAYER_COUNT = "プレイヤー人数"
ROW_ROLES = "役職"
ROW_DEFAULT_ROLE_COUNTS = "既定の役職人数"
ROW_STATUS = "状態"
ROW_PHASE = "フェーズ"
ROW_DAY = "日"
ROW_VERSION = "バージョン"
ROW_ALIVE = "生存者"
ROW_ELIMINATED = "退場者"
ROW_WINNER = "勝利陣営"
ROW_ROLE = "役職"
ROW_AVAILABLE_ACTIONS = "実行できる行動"
ROW_KNOWN_ROLES = "判明している役職"

EMPTY_VALUE = "-"
PROMPT_SPEECH = "発言内容"
MESSAGE_REPLAY_SOURCE_REQUIRED = "--timelineまたは--game-idを指定してください。"


def table_title_game(game_id: str) -> str:
    """Return the game-state table title."""
    return f"ゲーム {game_id}"


def table_title_observation(player_id: str) -> str:
    """Return the private-observation table title."""
    return f"観測情報 {player_id}"


def message_created_game(game_id: str) -> str:
    """Return the CLI created-game notice."""
    return f"ゲームを作成しました: [bold]{game_id}[/bold]"


def message_game_completed(*, winner: str, steps: int) -> str:
    """Return the CLI game-completed notice."""
    return f"[bold green]ゲームが終了しました[/bold green]: 勝利陣営={winner}, ステップ={steps}"


def message_timeline_item(*, sequence: int, event_type: str, payload: object) -> str:
    """Return one rich-formatted timeline item line."""
    return f"[dim]{sequence}[/dim] [bold]{event_type}[/bold] {payload}"


def message_next_offset(next_offset: int) -> str:
    """Return the next page offset notice."""
    return f"[dim]next offset: {next_offset}[/dim]"


def message_target_prompt(action_type: str) -> str:
    """Return the target prompt for an action type."""
    return f"{action_type}の対象ID"


MESSAGE_MAX_STEPS_MUST_BE_AT_LEAST_ONE = "max_stepsは1以上にしてください。"

MESSAGE_POLL_INTERVAL_MUST_BE_NON_NEGATIVE = "poll_intervalは0以上にしてください。"

MESSAGE_OUTPUT_FORMAT_MUST_BE_VALID = "出力形式はtable、json、jsonlから選んでください。"

MESSAGE_JSON_OUTPUT_CANNOT_FOLLOW = "継続取得ではjsonl出力を使用してください。"


def message_game_did_not_complete(max_steps: int) -> str:
    """Return a CLI max-step failure message."""
    return f"ゲームは{max_steps} APIステップ以内に終了しませんでした。"


def message_error_line(detail: str, suffix: str = "") -> str:
    """Return one CLI error line."""
    return f"エラー: {detail}{suffix}"
