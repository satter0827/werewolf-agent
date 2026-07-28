"""Public narration values derived from a persisted setup document."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from werewolf_agent.application.validation import non_blank


class _DefinitionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NarrationEventDefinition(_DefinitionModel):
    """Validated narration templates for one public event type."""

    templates: tuple[str, ...]

    @field_validator("templates")
    @classmethod
    def validate_templates(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Return non-empty narration templates."""
        templates = tuple(non_blank(item, "narration template") for item in value)
        if not templates:
            raise ValueError("narration templates are required")
        return templates


class NarrationProfileDefinition(_DefinitionModel):
    """Narration template groups keyed by public event type."""

    events: dict[str, NarrationEventDefinition] = Field(default_factory=dict)

    @field_validator("events")
    @classmethod
    def validate_events(
        cls, value: dict[str, NarrationEventDefinition]
    ) -> dict[str, NarrationEventDefinition]:
        """Return narration events with normalized unique keys."""
        return {non_blank(str(key), "narration event type"): item for key, item in value.items()}


__all__ = ["NarrationEventDefinition", "NarrationProfileDefinition"]
