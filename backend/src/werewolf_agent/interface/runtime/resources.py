"""Runtime TOML resource loading for interface settings."""

from __future__ import annotations

import tomllib
from importlib.resources import files
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from werewolf_agent.commons.shared.definitions import (
    FakeDecisionCatalog,
    GameDefinitions,
    GameRoleDefinitions,
    GameRuleDefinitions,
    LlmDefinitions,
    PlayerRoster,
    PromptDefinition,
)

TModel = TypeVar("TModel", bound=BaseModel)

SETTINGS_PACKAGE = "werewolf_agent.resources.settings"
SETTINGS_FILE = "defaults.toml"
GAME_DEFINITIONS_PACKAGE = "werewolf_agent.resources.game"
LLM_DEFINITIONS_PACKAGE = "werewolf_agent.resources.llm"
PROMPTS_PACKAGE = "werewolf_agent.resources.prompts"
STREAMLIT_PACKAGE = "werewolf_agent.resources.streamlit"
RULES_FILE = "rules.toml"
ROLES_FILE = "roles.toml"
PLAYERS_FILE = "players.toml"
PROMPT_FILE = "agent_decision.toml"
FAKE_RESPONSES_FILE = "fake_responses.toml"
STREAMLIT_I18N_FILE = "i18n.toml"


def load_packaged_defaults() -> dict[str, object]:
    """Load packaged runtime setting defaults."""
    return load_packaged_toml(SETTINGS_PACKAGE, SETTINGS_FILE)


def load_packaged_toml(package: str, file_name: str) -> dict[str, object]:
    """Load a packaged TOML resource."""
    resource = files(package).joinpath(file_name)
    with resource.open("rb") as file:
        return tomllib.load(file)


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


def load_streamlit_i18n(override_path: Path | None) -> dict[str, object]:
    """Load Streamlit UI translations from settings."""
    return (
        load_external_toml(override_path)
        if override_path is not None
        else load_packaged_toml(STREAMLIT_PACKAGE, STREAMLIT_I18N_FILE)
    )


def load_game_definitions(
    *,
    rules_path: Path | None,
    roles_path: Path | None,
) -> GameDefinitions:
    """Load game-only runtime definitions."""
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
            package=LLM_DEFINITIONS_PACKAGE,
            file_name=FAKE_RESPONSES_FILE,
            override_path=fake_responses_path,
        ),
    )


__all__ = [
    "load_external_toml",
    "load_game_definitions",
    "load_llm_definitions",
    "load_packaged_defaults",
    "load_packaged_toml",
    "load_streamlit_i18n",
    "load_toml_model",
]
