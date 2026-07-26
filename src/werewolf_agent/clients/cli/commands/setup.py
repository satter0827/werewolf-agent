"""Typer command handlers for game workflows."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Annotated

import toml  # type: ignore[import-untyped]
import typer
from pydantic import ValidationError

from werewolf_agent.adapters.factory import build_public_client
from werewolf_agent.clients.cli.commands.common import _output_format
from werewolf_agent.clients.cli.errors import run_app_command
from werewolf_agent.clients.cli.messages import (
    HELP_OUTPUT_FORMAT,
)
from werewolf_agent.clients.cli.output import (
    console,
    print_json,
    print_setup_options,
)
from werewolf_agent.clients.requests import build_custom_setup_request
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    GameSetupDocumentRequest,
    RuleCompositionSelection,
)
from werewolf_agent.settings import get_settings

logger = logging.getLogger(__name__)


def setup_options(
    output: Annotated[
        str | None,
        typer.Option("--output", help=HELP_OUTPUT_FORMAT),
    ] = None,
) -> None:
    """Print default game setup metadata."""
    run_app_command(
        lambda: print_setup_options(
            build_public_client(get_settings()).get_runtime_config().setup,
            output_format=_output_format(output, get_settings()),
        )
    )


def export_setup(
    preset: Annotated[str, typer.Option("--preset", help="出力するsetup preset ID")],
    output_file: Annotated[Path, typer.Option("--output-file", help="出力先TOML file")],
) -> None:
    """Export one preset as a complete editable TOML document."""
    run_app_command(lambda: _export_setup(preset, output_file))


def _export_setup(preset_id: str, output_file: Path) -> None:
    options = build_public_client(get_settings()).get_runtime_config().setup
    try:
        preset = next(item for item in options.setup_presets if item.id == preset_id)
    except StopIteration as exc:
        raise AppError(
            f"setup presetが見つかりません: {preset_id}",
            code=ErrorCode.CONFIG_INVALID_VALUE,
        ) from exc
    request = build_custom_setup_request(
        setup_options=options,
        role_counts=dict(preset.role_counts),
        rules=options.default_rules,
        scenario_id=preset.scenario_id,
        character_assignments={},
        rule_composition=RuleCompositionSelection(),
    )
    output_file.write_text(
        toml.dumps(request.setup.model_dump(mode="json")),
        encoding="utf-8",
    )
    console.print(f"設定を出力しました: {output_file}")


def validate_setup(
    setup_file: Annotated[Path, typer.Argument(help="検証するsetup TOML file")],
) -> None:
    """Validate a complete setup document without creating a game."""
    run_app_command(lambda: _validate_setup(setup_file, inspect=False))


def inspect_setup(
    setup_file: Annotated[Path, typer.Argument(help="確認するsetup TOML file")],
) -> None:
    """Validate and print a normalized setup summary."""
    run_app_command(lambda: _validate_setup(setup_file, inspect=True))


def _validate_setup(setup_file: Path, *, inspect: bool) -> None:
    try:
        with setup_file.open("rb") as file:
            setup = GameSetupDocumentRequest.model_validate(tomllib.load(file))
    except (OSError, tomllib.TOMLDecodeError, ValidationError) as exc:
        raise AppError(
            f"game setup TOMLが不正です: {exc}",
            code=ErrorCode.CONFIG_INVALID_VALUE,
        ) from exc
    result = build_public_client(get_settings()).validate_setup(setup)
    if not inspect:
        console.print("設定は有効です。")
        return
    print_json(
        result.model_dump(mode="json"),
        output_format="json",
    )
