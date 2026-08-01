"""Runtime TOML resource loading."""

from __future__ import annotations

import tomllib
from importlib.resources import files
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ConfigDict

from werewolf_agent.adapters.llm.definitions import PromptDefinition
from werewolf_agent.adapters.llm.fake_definitions import FakeDecisionCatalog
from werewolf_agent.application.setup_catalog import (
    SetupTemplateCatalog,
    SetupTemplateCatalogDefinition,
)
from werewolf_agent.setup import GameSetupDocument

TModel = TypeVar("TModel", bound=BaseModel)

FAKE_DEFINITIONS_PACKAGE = "werewolf_agent.adapters.llm.resources"
PROMPTS_PACKAGE = "werewolf_agent.adapters.llm.resources"
SETUPS_PACKAGE = "werewolf_agent.application.resources.setups"
CATALOG_FILE = "catalog.toml"
PROMPT_FILE = "agent_decision.toml"
FAKE_RESPONSES_FILE = "fake_responses.toml"
SETUP_CATALOG_FILE = "catalog.toml"


class LlmDefinitions(BaseModel):
    """Adapterがapplication profileとagent定義を合成したresource."""

    model_config = ConfigDict(extra="forbid", frozen=True)

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


def load_llm_definitions(
    *,
    prompt_path: Path | None,
    fake_responses_path: Path | None,
) -> LlmDefinitions:
    """Load LLM-only runtime definitions."""
    return LlmDefinitions(
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


def load_setup_template_catalog() -> SetupTemplateCatalog:
    """Load every complete packaged setup without implicit fallback."""
    definition = SetupTemplateCatalogDefinition.model_validate(
        load_packaged_toml(SETUPS_PACKAGE, SETUP_CATALOG_FILE)
    )
    documents = {
        template_id: GameSetupDocument.from_mapping(
            load_packaged_toml(SETUPS_PACKAGE, metadata.file)
        )
        for template_id, metadata in definition.templates.items()
    }
    return SetupTemplateCatalog(
        recommended_template_id=definition.recommended_template_id,
        template_order=definition.template_order,
        metadata=definition.templates,
        documents=documents,
    )


__all__ = [
    "LlmDefinitions",
    "load_external_text",
    "load_external_toml",
    "load_llm_definitions",
    "load_packaged_text",
    "load_packaged_toml",
    "load_setup_template_catalog",
    "load_toml_model",
]
