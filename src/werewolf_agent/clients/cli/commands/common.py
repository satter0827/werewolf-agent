"""Typer command handlers for game workflows."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import cast

import typer
from pydantic import ValidationError

from werewolf_agent.adapters.auth import require_supabase_client_config
from werewolf_agent.adapters.factory import build_game_client, build_public_client
from werewolf_agent.adapters.ports import GameClient
from werewolf_agent.clients.cli.constants import (
    CLI_OUTPUT_FORMAT_CHOICE_SET,
    CLI_OUTPUT_FORMAT_TABLE,
    MIN_PAGE_OFFSET,
)
from werewolf_agent.clients.cli.events import (
    LOG_CLI_ACTION_SUBMITTED,
)
from werewolf_agent.clients.cli.messages import (
    MESSAGE_OUTPUT_FORMAT_MUST_BE_VALID,
    MESSAGE_REPLAY_SOURCE_REQUIRED,
    PROMPT_SPEECH,
    message_target_prompt,
)
from werewolf_agent.clients.cli.output import (
    OutputFormat,
    print_observation,
    print_timeline,
)
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    PLAYER_ACTION_REQUEST_ADAPTER,
    CreateGameRequest,
    DeliberationLevel,
    GameSetupDocumentRequest,
    GameSetupSelectionRequest,
    GameTimelineItem,
    InlineSetupRequest,
    TemplateSetupRequest,
)
from werewolf_agent.observability.constants import (
    EVENT_OUTCOME_SUCCESS,
)
from werewolf_agent.settings import AppSettings, get_settings

logger = logging.getLogger(__name__)


def _client() -> GameClient:
    settings = get_settings()
    require_supabase_client_config(settings)
    return build_game_client(settings)


def _create_request(
    *,
    seed: int | None,
    manual_player: str | None,
    setup_file: Path | None = None,
    template_id: str | None = None,
    deliberation_level: DeliberationLevel = "standard",
) -> CreateGameRequest:
    settings = get_settings()
    selection: GameSetupSelectionRequest
    if setup_file is not None:
        try:
            with setup_file.open("rb") as file:
                payload = tomllib.load(file)
            selection = InlineSetupRequest(
                mode="inline",
                document=GameSetupDocumentRequest.model_validate(payload),
            )
        except (OSError, tomllib.TOMLDecodeError, ValidationError) as exc:
            raise AppError(
                "game setup TOMLを読み込めませんでした。",
                code=ErrorCode.CONFIG_INVALID_VALUE,
            ) from exc
    else:
        catalog = build_public_client(settings).get_setup_catalog()
        selection = TemplateSetupRequest(
            mode="template",
            template_id=template_id or catalog.recommended_template_id,
        )
    return CreateGameRequest(
        seed=seed,
        manual_player_id=manual_player,
        setup=selection,
        deliberation_level=deliberation_level,
    )


def _prompt_and_submit_manual_action(
    *,
    client: GameClient,
    game_id: str,
    player_id: str,
    output_format: OutputFormat,
) -> None:
    observation = client.get_private_observation(
        game_id,
        player_id,
    )
    actions = observation.observation.available_actions
    if not actions:
        return
    if output_format == CLI_OUTPUT_FORMAT_TABLE:
        print_observation(observation)
    selected = actions[0]
    action_type = selected.type
    ability_id = selected.ability_id
    action_key = selected.key
    target_id = None
    message = None
    response_to_id = None
    if action_type == "speech":
        message = typer.prompt(PROMPT_SPEECH)
        round_ = observation.observation.discussion_round
        if round_ is not None and round_.reference_ids:
            response_to_id = round_.reference_ids[0]
    elif action_type != "pass":
        target_id = typer.prompt(message_target_prompt(action_key))
    response = client.submit_player_action(
        game_id,
        player_id,
        PLAYER_ACTION_REQUEST_ADAPTER.validate_python(
            _action_payload(
                action_type,
                ability_id=ability_id,
                target_id=target_id,
                message=message,
                reason=(typer.prompt("投票理由") if action_type == "vote" else None),
                response_to_id=response_to_id,
            )
        ),
    )
    logger.info(
        LOG_CLI_ACTION_SUBMITTED,
        extra={
            "event_action": LOG_CLI_ACTION_SUBMITTED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_id": game_id,
            "has_target": target_id is not None,
            "has_message": bool(message),
        },
    )
    if output_format == CLI_OUTPUT_FORMAT_TABLE:
        print_timeline(response.timeline)


def _action_payload(
    action_type: str,
    *,
    ability_id: str | None,
    target_id: str | None,
    message: str | None,
    reason: str | None,
    response_to_id: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"type": action_type}
    if ability_id is not None:
        payload["ability_id"] = ability_id
    if target_id is not None:
        payload["target_id"] = target_id
    if message is not None:
        payload["message"] = message
    if reason is not None:
        payload["reason"] = reason
    if response_to_id is not None:
        payload["response_to_id"] = response_to_id
    return payload


def _load_replay_items(
    timeline_file: Path | None,
    *,
    game_id: str | None,
    client: GameClient,
    timeline_limit: int,
) -> list[GameTimelineItem]:
    if timeline_file is not None:
        return [
            GameTimelineItem.model_validate_json(line)
            for line in timeline_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if game_id is not None:
        return client.get_timeline(
            game_id,
            after=MIN_PAGE_OFFSET,
            limit=timeline_limit,
        ).items
    raise AppError(MESSAGE_REPLAY_SOURCE_REQUIRED, code=ErrorCode.CONFIG_INVALID_VALUE)


def _output_format(value: str | None, settings: AppSettings) -> OutputFormat:
    raw_value = value or settings.cli_output_format
    if raw_value not in CLI_OUTPUT_FORMAT_CHOICE_SET:
        raise AppError(MESSAGE_OUTPUT_FORMAT_MUST_BE_VALID, code=ErrorCode.CONFIG_INVALID_VALUE)
    return cast(OutputFormat, raw_value)
