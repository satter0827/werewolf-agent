"""Fake chat-model fixture definitions owned by the LLM adapter."""

from __future__ import annotations

from collections.abc import Mapping
from string import Template

from pydantic import BaseModel, ConfigDict, Field, field_validator

from werewolf_agent.agents.constants import MIN_VERSION
from werewolf_agent.agents.validation import non_blank


class _FakeDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FakeDecisionTemplate(_FakeDefinition):
    """One deterministic fake chat response template."""

    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        return non_blank(value, "fake decision template")

    def render(self, context: Mapping[str, object]) -> str:
        values = {key: str(value) for key, value in context.items()}
        return Template(self.content).safe_substitute(values).strip()


class FakeDecisionCatalog(_FakeDefinition):
    """Fixture response catalog used only by FakeDecisionModel."""

    name: str
    version: int = Field(ge=MIN_VERSION)
    alias: str
    tags: dict[str, str] = Field(default_factory=dict)
    templates: dict[str, tuple[FakeDecisionTemplate, ...]]

    @field_validator("name", "alias")
    @classmethod
    def validate_non_blank_text(cls, value: str) -> str:
        """Return normalized fake catalog metadata."""
        return non_blank(value, "fake decision metadata")

    @field_validator("templates", mode="before")
    @classmethod
    def normalize_template_keys(cls, value: object) -> object:
        """Normalize string and list template declarations."""
        if not isinstance(value, Mapping):
            return value
        normalized: dict[str, object] = {}
        for key, item in value.items():
            action_type = non_blank(str(key), "fake decision action type")
            raw_items = item if isinstance(item, list) else [item]
            normalized[action_type] = [
                {"content": raw_item} if isinstance(raw_item, str) else raw_item
                for raw_item in raw_items
            ]
        return normalized

    @field_validator("templates")
    @classmethod
    def validate_templates(
        cls,
        value: dict[str, tuple[FakeDecisionTemplate, ...]],
    ) -> dict[str, tuple[FakeDecisionTemplate, ...]]:
        """Require a fallback fixture and non-empty template pools."""
        if "pass" not in value:
            raise ValueError("templates.pass is required")
        templates: dict[str, tuple[FakeDecisionTemplate, ...]] = {}
        for key, items in value.items():
            action_type = non_blank(key, "fake decision action type")
            if not items:
                raise ValueError(f"templates.{action_type} must not be empty")
            templates[action_type] = tuple(items)
        return templates

    def render(
        self,
        action_type: str,
        *,
        context: Mapping[str, object],
        selector: int = 0,
    ) -> str:
        """Render one deterministic response for the requested action."""
        template_pool = self.templates.get(action_type) or self.templates["pass"]
        return template_pool[selector % len(template_pool)].render(context)


__all__ = ["FakeDecisionCatalog"]
