"""Command-line interface entry point for Werewolf Agent."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Final

import typer
from pydantic import ValidationError

from werewolf_agent.clients.cli.commands import (
    advance,
    doctor,
    games,
    new,
    play,
    replay,
    setup_options,
    show,
    timeline,
)
from werewolf_agent.clients.cli.commands.action import action
from werewolf_agent.clients.cli.commands.admin import (
    llm_traces,
    llm_usage,
    operation,
    replay_verify,
    reveal,
)
from werewolf_agent.clients.cli.commands.setup import export_setup, inspect_setup, validate_setup
from werewolf_agent.clients.cli.commands.system import status
from werewolf_agent.clients.cli.events import (
    LOG_CLI_APPLICATION_STARTED,
)
from werewolf_agent.clients.cli.messages import (
    HELP_APP,
    message_error_line,
)
from werewolf_agent.clients.presentation import CLI_COMMAND_FEATURES, implements_features
from werewolf_agent.contracts import ConfigError
from werewolf_agent.observability import configure_entrypoint_logging
from werewolf_agent.observability.constants import EVENT_OUTCOME_SUCCESS
from werewolf_agent.settings import (
    settings_error_detail,
)

logger = logging.getLogger(__name__)

app = typer.Typer(
    help=HELP_APP,
    no_args_is_help=True,
)


@app.callback()
def main(ctx: typer.Context) -> None:
    """Werewolf Agent command group."""
    try:
        settings = configure_entrypoint_logging(
            default_log_file_name="cli.jsonl",
            service_name="werewolf-agent-cli",
        )
    except ValidationError as exc:
        error = ConfigError(settings_error_detail(exc))
        typer.echo(message_error_line(error.detail), err=True)
        raise typer.Exit(code=1) from exc
    logger.info(
        LOG_CLI_APPLICATION_STARTED,
        extra={
            "event_action": LOG_CLI_APPLICATION_STARTED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "cli_command": ctx.invoked_subcommand,
            "log_level": settings.log_level,
            "log_output": settings.log_output,
            "log_file_path": str(settings.log_file_path),
            "log_third_party_level": settings.log_third_party_level,
        },
    )


system_app = typer.Typer(help="実行環境を診断します。")
setup_app = typer.Typer(help="ゲーム作成に使える設定を確認します。")
game_app = typer.Typer(help="ゲームを作成・操作します。")
records_app = typer.Typer(help="公開記録を取得・再生します。")
admin_app = typer.Typer(help="管理者専用の診断と検証を行います。")

CLI_COMMAND_IMPLEMENTATIONS: Final[dict[str, Callable[..., Any]]] = {}


def _register_feature_command(
    command_group: typer.Typer,
    *,
    path: str,
    name: str,
    handler: Callable[..., Any],
    help_text: str,
) -> None:
    """Register one command and attach its declared API feature ownership."""
    if path in CLI_COMMAND_IMPLEMENTATIONS:
        raise ValueError(f"duplicate CLI command path: {path}")
    decorated = implements_features(*CLI_COMMAND_FEATURES[path])(handler)
    CLI_COMMAND_IMPLEMENTATIONS[path] = decorated
    command_group.command(name=name, help=help_text)(decorated)


system_app.command(name="doctor", help="ローカル設定とresourceを検査します。")(doctor)
setup_app.command(name="export", help="templateを編集可能なTOMLへ出力します。")(export_setup)
for _group, _path, _name, _handler, _help in (
    (system_app, "system status", "status", status, "APIと依存先の可用性を表示します。"),
    (setup_app, "setup show", "show", setup_options, "選択可能なゲーム設定を表示します。"),
    (setup_app, "setup validate", "validate", validate_setup, "setup TOMLを検証します。"),
    (
        setup_app,
        "setup inspect",
        "inspect",
        inspect_setup,
        "setup TOMLの正規化結果を表示します。",
    ),
    (game_app, "game create", "create", new, "ゲームを作成します。"),
    (game_app, "game list", "list", games, "ゲーム一覧を表示します。"),
    (game_app, "game show", "show", show, "公開game状態を表示します。"),
    (game_app, "game action", "action", action, "manual playerの行動を送信します。"),
    (game_app, "game advance", "advance", advance, "ゲームを1段階進めます。"),
    (game_app, "game play", "play", play, "ゲームを作成して完了まで進めます。"),
    (records_app, "records timeline", "timeline", timeline, "公開timelineを取得します。"),
    (records_app, "records replay", "replay", replay, "公開timelineを物語として再生します。"),
    (admin_app, "admin reveal", "reveal", reveal, "完全なgame状態を取得します。"),
    (
        admin_app,
        "admin replay-verify",
        "replay-verify",
        replay_verify,
        "保存済みreplayの決定性を検証します。",
    ),
    (admin_app, "admin operation", "operation", operation, "operationの診断情報を取得します。"),
    (
        admin_app,
        "admin llm-traces",
        "llm-traces",
        llm_traces,
        "秘匿本文を除いたLLM traceを取得します。",
    ),
    (admin_app, "admin llm-usage", "llm-usage", llm_usage, "game単位のLLM利用量を取得します。"),
):
    _register_feature_command(
        _group,
        path=_path,
        name=_name,
        handler=_handler,
        help_text=_help,
    )

app.add_typer(system_app, name="system")
app.add_typer(setup_app, name="setup")
app.add_typer(game_app, name="game")
app.add_typer(records_app, name="records")
app.add_typer(admin_app, name="admin")


if __name__ == "__main__":
    app()
