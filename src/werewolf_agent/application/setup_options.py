"""Setup catalog, validation, preview, and create-command preparation."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import Literal

from werewolf_agent.application.constants import DeliberationLevel
from werewolf_agent.application.errors import ConfigError
from werewolf_agent.application.models import (
    CreateGameCommand,
    GameApplicationConfig,
    GameSetupOptionsResult,
    GeneratedPlayerInput,
    PlayerPreviewResult,
    SetupValidationResult,
)
from werewolf_agent.application.setup_catalog import SetupTemplateCatalog
from werewolf_agent.domain import CORE_RULE_PACK_ID
from werewolf_agent.setup import GameSetupDocument, checksum_payload, generate_players

ABILITY_KINDS = (
    "attack",
    "inspect",
    "protect",
    "eliminate",
    "knowledge",
    "death_reaction",
    "immunity",
    "vulnerability",
)


def setup_catalog_options(
    config: GameApplicationConfig,
    catalog: SetupTemplateCatalog,
) -> GameSetupOptionsResult:
    """Return editor metadata without constructing any implicit setup."""
    return GameSetupOptionsResult(
        player_count={"min": config.min_players, "max": config.max_players},
        recommended_template_id=catalog.recommended_template_id,
        template_order=catalog.template_order,
        templates={
            template_id: {
                "name": metadata.name,
                "summary": metadata.summary,
            }
            for template_id, metadata in catalog.metadata.items()
        },
        ability_kinds=ABILITY_KINDS,
    )


def validate_setup_document(payload: Mapping[str, object]) -> SetupValidationResult:
    """ゲームを作成せず、一つの完全setupを検証して正規化する."""
    try:
        setup = GameSetupDocument.from_mapping(payload)
    except (TypeError, ValueError) as exc:
        raise ConfigError(str(exc)) from exc
    mechanics = setup.mechanics
    warnings: list[str] = []
    werewolf_count = sum(
        mechanics.role_counts[role_id]
        for role_id, role in mechanics.roles.items()
        if role.identity_faction == "werewolf"
    )
    player_count = sum(mechanics.role_counts.values())
    if werewolf_count * 3 > player_count:
        warnings.append("人狼陣営が多いため、短いゲームになる可能性があります。")
    return SetupValidationResult(
        schema_version=setup.schema_version,
        player_count=player_count,
        theme_id=setup.theme.id,
        theme_name=setup.theme.name,
        role_ids=tuple(sorted(mechanics.roles)),
        ability_ids=tuple(sorted(mechanics.abilities)),
        setup_checksum=checksum_payload(setup.to_mapping()),
        mechanics_checksum=checksum_payload(mechanics.to_mapping()),
        warnings=tuple(warnings),
    )


def parse_setup_document(payload: Mapping[str, object]) -> GameSetupDocument:
    """外部入力をapplicationが受理する完全setupへ変換する."""
    try:
        return GameSetupDocument.from_mapping(payload)
    except (TypeError, ValueError) as exc:
        raise ConfigError(str(exc)) from exc


def preview_players(setup: GameSetupDocument, *, seed: int | None) -> PlayerPreviewResult:
    """Generate a public-safe roster preview and return the concrete seed."""
    concrete_seed = secrets.randbits(63) if seed is None else seed
    players = generate_players(
        setup.player_generation,
        player_count=sum(setup.mechanics.role_counts.values()),
        seed=concrete_seed,
    )
    payload = tuple(player.public_payload() for player in players)
    return PlayerPreviewResult(
        seed=concrete_seed,
        players=payload,
        roster_checksum=checksum_payload(payload),
    )


def prepare_create_command(
    setup: GameSetupDocument,
    *,
    seed: int | None,
    manual_player_id: str | None,
    llm_mode: Literal["fake", "paid"],
    deliberation_level: DeliberationLevel,
    rule_pack_provider_id: str = CORE_RULE_PACK_ID,
) -> CreateGameCommand:
    """Resolve public roster values and a private game seed before queueing."""
    roster_seed = secrets.randbits(63) if seed is None else seed
    private_seed = secrets.randbits(63)
    generated = generate_players(
        setup.player_generation,
        player_count=sum(setup.mechanics.role_counts.values()),
        seed=roster_seed,
        private_strategy_seed=private_seed,
    )
    players = tuple(
        GeneratedPlayerInput.model_validate(player.private_payload()) for player in generated
    )
    return CreateGameCommand(
        seed=private_seed,
        setup=setup,
        players=players,
        setup_checksum=checksum_payload(setup.to_mapping()),
        mechanics_checksum=checksum_payload(setup.mechanics.to_mapping()),
        roster_checksum=checksum_payload([player.public_payload() for player in players]),
        manual_player_id=manual_player_id,
        llm_mode=llm_mode,
        deliberation_level=deliberation_level,
        rule_pack_provider_id=rule_pack_provider_id,
    )


__all__ = [
    "ABILITY_KINDS",
    "parse_setup_document",
    "prepare_create_command",
    "preview_players",
    "setup_catalog_options",
    "validate_setup_document",
]
