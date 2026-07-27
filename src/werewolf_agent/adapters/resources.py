"""Runtime TOML resource loading."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from typing import TypeVar, cast

from pydantic import BaseModel, ConfigDict

from werewolf_agent.adapters.llm.fake_definitions import FakeDecisionCatalog
from werewolf_agent.agents.definitions import PromptDefinition
from werewolf_agent.application.definitions import (
    GameCatalogDefinitions,
    GameDefinitions,
    GameRoleDefinitions,
    GameRuleDefinitions,
    PlayerRoster,
)

TModel = TypeVar("TModel", bound=BaseModel)

GAME_DEFINITIONS_PACKAGE = "werewolf_agent.application.resources.game"
PRESENTATION_DEFINITIONS_PACKAGE = "werewolf_agent.application.resources.presentation"
LLM_DEFINITIONS_PACKAGE = "werewolf_agent.agents.resources.llm"
FAKE_DEFINITIONS_PACKAGE = "werewolf_agent.adapters.llm.resources"
PROMPTS_PACKAGE = "werewolf_agent.agents.resources.prompts"
RULES_FILE = "rules.toml"
ROLES_FILE = "roles.toml"
ABILITIES_FILE = "abilities.toml"
CATALOG_FILE = "catalog.toml"
PLAYERS_FILE = "players.toml"
PROMPT_FILE = "agent_decision.toml"
FAKE_RESPONSES_FILE = "fake_responses.toml"


class LlmDefinitions(BaseModel):
    """Adapterがapplication profileとagent定義を合成したresource."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    players: PlayerRoster
    prompt: PromptDefinition
    fake_responses: FakeDecisionCatalog


def load_packaged_toml(package: str, file_name: str) -> dict[str, object]:
    """Load a packaged TOML resource."""
    resource = files(package).joinpath(file_name)
    with resource.open("rb") as file:
        return tomllib.load(file)


def load_packaged_text(package: str, file_name: str) -> str:
    """Load a packaged text resource."""
    resource = files(package).joinpath(file_name)
    return resource.read_text(encoding="utf-8")


def load_toml_model(
    model_type: type[TModel],
    *,
    package: str,
    file_name: str,
    override_path: Path | None,
) -> TModel:
    """Load a TOML model from an external path or packaged resource."""
    data = (
        load_external_toml(override_path)
        if override_path is not None
        else load_packaged_toml(
            package,
            file_name,
        )
    )
    return model_type.model_validate(data)


def load_external_toml(path: Path) -> dict[str, object]:
    """Load an external TOML file."""
    with path.open("rb") as file:
        return tomllib.load(file)


def load_external_text(path: Path) -> str:
    """Load an external text file."""
    return path.read_text(encoding="utf-8")


def load_game_definitions(
    *,
    rules_path: Path | None,
    roles_path: Path | None,
    catalog_path: Path | None = None,
    abilities_path: Path | None = None,
) -> GameDefinitions:
    """Load game-only runtime definitions."""
    presentation_data = (
        load_external_toml(catalog_path)
        if catalog_path is not None
        else load_packaged_toml(PRESENTATION_DEFINITIONS_PACKAGE, CATALOG_FILE)
    )
    ability_data = (
        load_external_toml(abilities_path)
        if abilities_path is not None
        else load_packaged_toml(GAME_DEFINITIONS_PACKAGE, ABILITIES_FILE)
    )
    ability_definitions = cast(
        Mapping[str, Mapping[str, object]],
        ability_data.get("abilities") or {},
    )
    catalog_data = {
        **presentation_data,
        "abilities": {
            ability_id: dict(definition) for ability_id, definition in ability_definitions.items()
        },
    }
    return GameDefinitions(
        rules=load_toml_model(
            GameRuleDefinitions,
            package=GAME_DEFINITIONS_PACKAGE,
            file_name=RULES_FILE,
            override_path=rules_path,
        ),
        roles=load_toml_model(
            GameRoleDefinitions,
            package=GAME_DEFINITIONS_PACKAGE,
            file_name=ROLES_FILE,
            override_path=roles_path,
        ),
        catalog=GameCatalogDefinitions.model_validate(catalog_data),
    )


def load_llm_definitions(
    *,
    players_path: Path | None,
    prompt_path: Path | None,
    fake_responses_path: Path | None,
) -> LlmDefinitions:
    """Load LLM-only runtime definitions."""
    return LlmDefinitions(
        players=load_toml_model(
            PlayerRoster,
            package=LLM_DEFINITIONS_PACKAGE,
            file_name=PLAYERS_FILE,
            override_path=players_path,
        ),
        prompt=load_toml_model(
            PromptDefinition,
            package=PROMPTS_PACKAGE,
            file_name=PROMPT_FILE,
            override_path=prompt_path,
        ),
        fake_responses=load_toml_model(
            FakeDecisionCatalog,
            package=FAKE_DEFINITIONS_PACKAGE,
            file_name=FAKE_RESPONSES_FILE,
            override_path=fake_responses_path,
        ),
    )


__all__ = [
    "LlmDefinitions",
    "load_external_text",
    "load_external_toml",
    "load_game_definitions",
    "load_llm_definitions",
    "load_packaged_text",
    "load_packaged_toml",
    "load_toml_model",
]
