"""Rich output helpers for the command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from werewolf_agent.clients.cli.constants import (
    CLI_OUTPUT_FORMAT_JSONL,
    CLI_OUTPUT_FORMAT_TABLE,
    JSON_SEPARATORS,
    PYDANTIC_JSON_MODE,
    CliOutputFormat,
)
from werewolf_agent.clients.cli.messages import (
    COLUMN_ACTOR,
    COLUMN_DAY,
    COLUMN_EVENT,
    COLUMN_FIELD,
    COLUMN_GAME,
    COLUMN_PAYLOAD,
    COLUMN_PHASE,
    COLUMN_SEQUENCE,
    COLUMN_STATUS,
    COLUMN_TURNS,
    COLUMN_VALUE,
    COLUMN_WINNER,
    EMPTY_VALUE,
    ROW_ALIVE,
    ROW_AVAILABLE_ACTIONS,
    ROW_DAY,
    ROW_DEFAULT_ROLE_COUNTS,
    ROW_ELIMINATED,
    ROW_KNOWN_ROLES,
    ROW_PHASE,
    ROW_PLAYER_COUNT,
    ROW_ROLE,
    ROW_ROLES,
    ROW_STATUS,
    ROW_VERSION,
    ROW_WINNER,
    TABLE_TITLE_API_HEALTH,
    TABLE_TITLE_GAME_SETUP,
    TABLE_TITLE_GAME_TIMELINE,
    TABLE_TITLE_GAMES,
    message_timeline_item,
    table_title_game,
    table_title_observation,
)
from werewolf_agent.contracts.api import RuntimeStatusResponse
from werewolf_agent.contracts.schemas import (
    GameSetupOptionsResponse,
    GameTimelineItem,
    PlayerObservationResponse,
    PublicGameState,
    PublicGameSummary,
)

console = Console(legacy_windows=False)
OutputFormat = CliOutputFormat


def print_health(
    payload: dict[str, str],
    *,
    output_format: OutputFormat = CLI_OUTPUT_FORMAT_TABLE,
) -> None:
    """Print API health."""
    if output_format != CLI_OUTPUT_FORMAT_TABLE:
        print_json(payload, output_format=output_format)
        return

    table = Table(title=TABLE_TITLE_API_HEALTH)
    table.add_column(COLUMN_FIELD, style="cyan", no_wrap=True)
    table.add_column(COLUMN_VALUE, overflow="fold")
    for key, value in payload.items():
        table.add_row(key, value)
    console.print(table)


def print_setup_options(
    options: GameSetupOptionsResponse,
    *,
    output_format: OutputFormat = CLI_OUTPUT_FORMAT_TABLE,
) -> None:
    """Print public setup metadata."""
    if output_format != CLI_OUTPUT_FORMAT_TABLE:
        print_json(options, output_format=output_format)
        return

    table = Table(title=TABLE_TITLE_GAME_SETUP)
    table.add_column(COLUMN_FIELD, style="cyan", no_wrap=True)
    table.add_column(COLUMN_VALUE, overflow="fold")
    table.add_row(ROW_PLAYER_COUNT, str(options.player_count))
    table.add_row(ROW_ROLES, ", ".join(role.id for role in options.roles))
    table.add_row(
        "役職の詳細",
        "\n".join(
            f"{role.name} ({role.id}): {role.description} / 能力={','.join(role.abilities) or '-'}"
            for role in options.roles
        ),
    )
    table.add_row(
        "能力",
        "\n".join(
            f"{ability.name} ({ability.id}): {ability.description}" for ability in options.abilities
        )
        or EMPTY_VALUE,
    )
    table.add_row(
        "シナリオ",
        "\n".join(
            f"{scenario.name} ({scenario.id}): {scenario.summary}" for scenario in options.scenarios
        )
        or EMPTY_VALUE,
    )
    table.add_row(
        "プリセット",
        "\n".join(
            f"{preset.name} ({preset.id}): {preset.role_counts}" for preset in options.setup_presets
        )
        or EMPTY_VALUE,
    )
    table.add_row(
        "キャラクター",
        ", ".join(f"{character.name} ({character.id})" for character in options.characters)
        or EMPTY_VALUE,
    )
    table.add_row(ROW_DEFAULT_ROLE_COUNTS, str(options.default_role_counts))
    table.add_row("ローカルルール", str(options.default_rules.model_dump(mode="json")))
    table.add_row("既定のシナリオ", options.default_scenario_id or EMPTY_VALUE)
    table.add_row("既定のプリセット", options.default_setup_preset_id or EMPTY_VALUE)
    table.add_row("既定のナレーション", options.default_narration_mode)
    composition = options.rule_composition
    table.add_row(
        "フェーズ順序",
        "\n".join(
            f"{item.name} ({item.id}): {item.description} / {', '.join(item.phases)}"
            for item in composition.phase_orders
        ),
    )
    table.add_row(
        "行動判定ポリシー",
        _policy_option_lines(composition.action_policies),
    )
    table.add_row(
        "行動解決ポリシー",
        _policy_option_lines(composition.resolution_policies),
    )
    table.add_row(
        "フェーズ進行ポリシー",
        _policy_option_lines(composition.phase_policies),
    )
    table.add_row(
        "勝敗判定ポリシー",
        _policy_option_lines(composition.victory_policies),
    )
    table.add_row(
        "公開範囲ポリシー",
        _policy_option_lines(composition.visibility_policies),
    )
    console.print(table)


def print_runtime_status(
    status: RuntimeStatusResponse,
    *,
    output_format: OutputFormat = CLI_OUTPUT_FORMAT_TABLE,
) -> None:
    """Print runtime component availability and safe reason codes."""
    if output_format != CLI_OUTPUT_FORMAT_TABLE:
        print_json(status, output_format=output_format)
        return
    component_names = {
        "api": "API",
        "authentication": "認証",
        "database": "データベース",
        "operation_queue": "処理キュー",
    }
    status_names = {
        "available": "利用可能",
        "degraded": "一部利用可能",
        "unavailable": "利用不可",
    }
    table = Table(title=f"システム状態: {status_names[status.status]}")
    table.add_column("構成要素", style="cyan", no_wrap=True)
    table.add_column("状態", no_wrap=True)
    table.add_column("理由コード", overflow="fold")
    for component in status.components:
        table.add_row(
            component_names[component.component],
            status_names[component.status],
            component.reason_code or EMPTY_VALUE,
        )
    console.print(table)


def _policy_option_lines(options: list[Any]) -> str:
    return "\n".join(f"{item.name} ({item.id}): {item.description}" for item in options)


def print_state(
    state: PublicGameState,
    *,
    output_format: OutputFormat = CLI_OUTPUT_FORMAT_TABLE,
) -> None:
    """Print a compact public game state table."""
    if output_format != CLI_OUTPUT_FORMAT_TABLE:
        print_json(state, output_format=output_format)
        return

    table = Table(title=table_title_game(state.game_id))
    table.add_column(COLUMN_FIELD, style="cyan", no_wrap=True)
    table.add_column(COLUMN_VALUE, overflow="fold")
    table.add_row(ROW_STATUS, state.status)
    table.add_row(ROW_PHASE, state.phase)
    table.add_row(ROW_DAY, str(state.day))
    table.add_row(ROW_VERSION, str(state.version))
    table.add_row(ROW_ALIVE, ", ".join(state.alive_player_ids) or EMPTY_VALUE)
    table.add_row(ROW_ELIMINATED, ", ".join(state.eliminated_player_ids) or EMPTY_VALUE)
    table.add_row(ROW_WINNER, state.winner or EMPTY_VALUE)
    console.print(table)


def print_observation(
    response: PlayerObservationResponse,
    *,
    output_format: OutputFormat = CLI_OUTPUT_FORMAT_TABLE,
) -> None:
    """Print one private observation."""
    if output_format != CLI_OUTPUT_FORMAT_TABLE:
        print_json(response, output_format=output_format)
        return

    observation = response.observation
    raw_me = observation.get("me")
    me = raw_me if isinstance(raw_me, dict) else {}
    table = Table(title=table_title_observation(response.player_id))
    table.add_column(COLUMN_FIELD, style="cyan", no_wrap=True)
    table.add_column(COLUMN_VALUE, overflow="fold")
    table.add_row(ROW_PHASE, str(observation.get("phase", EMPTY_VALUE)))
    table.add_row(ROW_DAY, str(observation.get("day", EMPTY_VALUE)))
    table.add_row(ROW_ROLE, str(me.get("role", EMPTY_VALUE)))
    table.add_row(
        ROW_AVAILABLE_ACTIONS,
        ", ".join(observation.get("available_actions") or []) or EMPTY_VALUE,
    )
    table.add_row(ROW_KNOWN_ROLES, str(observation.get("known_roles") or {}))
    console.print(table)


def consume_timeline(
    items: list[GameTimelineItem],
    *,
    next_after: int,
    log_jsonl: Path | None,
    show_items: bool,
    output_format: OutputFormat = CLI_OUTPUT_FORMAT_TABLE,
) -> int:
    """Print and optionally persist public timeline items."""
    if log_jsonl is not None:
        log_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with log_jsonl.open("a", encoding="utf-8") as file:
            for item in items:
                file.write(item.model_dump_json() + "\n")

    if show_items:
        print_timeline(items, output_format=output_format)
    return next_after


def print_timeline(
    items: list[GameTimelineItem],
    *,
    output_format: OutputFormat = CLI_OUTPUT_FORMAT_TABLE,
) -> None:
    """Print public timeline items."""
    if output_format != CLI_OUTPUT_FORMAT_TABLE:
        print_json(items, output_format=output_format)
        return

    for item in items:
        console.print(
            message_timeline_item(
                sequence=item.sequence,
                event_type=item.event_type,
                payload=item.payload,
            )
        )


def print_game_summaries(
    games: list[PublicGameSummary],
    *,
    output_format: OutputFormat = CLI_OUTPUT_FORMAT_TABLE,
) -> None:
    """Print public game summaries."""
    if output_format != CLI_OUTPUT_FORMAT_TABLE:
        print_json(games, output_format=output_format)
        return

    table = Table(title=TABLE_TITLE_GAMES)
    table.add_column(COLUMN_GAME, overflow="fold")
    table.add_column(COLUMN_STATUS, no_wrap=True)
    table.add_column(COLUMN_PHASE, no_wrap=True)
    table.add_column(COLUMN_DAY, justify="right")
    table.add_column(COLUMN_WINNER, no_wrap=True)
    table.add_column(COLUMN_TURNS, justify="right")
    for game in games:
        table.add_row(
            game.game_id,
            game.status,
            game.phase,
            str(game.day),
            game.winner or EMPTY_VALUE,
            str(game.turn_count),
        )
    console.print(table)


def print_timeline_table(
    items: list[GameTimelineItem],
    *,
    output_format: OutputFormat = CLI_OUTPUT_FORMAT_TABLE,
) -> None:
    """Print public timeline records in a table."""
    if output_format != CLI_OUTPUT_FORMAT_TABLE:
        print_json(items, output_format=output_format)
        return

    table = Table(title=TABLE_TITLE_GAME_TIMELINE)
    table.add_column(COLUMN_SEQUENCE, justify="right", no_wrap=True)
    table.add_column(COLUMN_EVENT, no_wrap=True)
    table.add_column(COLUMN_PHASE, no_wrap=True)
    table.add_column(COLUMN_ACTOR, overflow="fold")
    table.add_column(COLUMN_PAYLOAD, overflow="fold")
    for item in items:
        table.add_row(
            str(item.sequence),
            item.event_type,
            item.phase or EMPTY_VALUE,
            item.actor_id or EMPTY_VALUE,
            str(item.payload),
        )
    console.print(table)


def print_json(value: Any, *, output_format: OutputFormat) -> None:
    """Print JSON or JSONL for script-friendly command output."""
    if output_format == CLI_OUTPUT_FORMAT_JSONL:
        values = value if isinstance(value, list) else [value]
        for item in values:
            print(_json_line(item))
        return
    print(json.dumps(_json_value(value), ensure_ascii=False, indent=2, default=str))


def _json_line(value: Any) -> str:
    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        default=str,
        separators=JSON_SEPARATORS,
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode=PYDANTIC_JSON_MODE, exclude_none=True)
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value
