"""Read-only catalog of complete packaged setup templates."""

from __future__ import annotations

from typing import Self

from pydantic import ConfigDict, field_validator, model_validator

from werewolf_agent.application.models.base import ApplicationModel
from werewolf_agent.application.setup_document import GameSetupDocument
from werewolf_agent.application.validation import non_blank


class SetupTemplateMetadata(ApplicationModel):
    """Public metadata for one packaged template."""

    name: str
    summary: str
    file: str

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("name", "summary", "file")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """Return non-empty template metadata text."""
        return non_blank(value, "template metadata")


class SetupTemplateCatalogDefinition(ApplicationModel):
    """Catalog resource before template documents are loaded."""

    recommended_template_id: str
    template_order: tuple[str, ...]
    templates: dict[str, SetupTemplateMetadata]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """Require explicit ordering of every catalog template."""
        if set(self.template_order) != set(self.templates):
            raise ValueError("template_order must contain every template exactly once")
        if self.recommended_template_id not in self.templates:
            raise ValueError("recommended_template_id must reference a template")
        return self


class SetupTemplateCatalog(ApplicationModel):
    """Validated packaged templates ready for application use."""

    recommended_template_id: str
    template_order: tuple[str, ...]
    metadata: dict[str, SetupTemplateMetadata]
    documents: dict[str, GameSetupDocument]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_documents(self) -> Self:
        """Require metadata and documents for every ordered template."""
        if set(self.metadata) != set(self.documents) or set(self.template_order) != set(
            self.documents
        ):
            raise ValueError("template metadata and documents must have identical IDs")
        return self

    def require_document(self, template_id: str) -> GameSetupDocument:
        """Return one complete template or fail without fallback."""
        return self.documents[non_blank(template_id, "template_id")]


__all__ = [
    "SetupTemplateCatalog",
    "SetupTemplateCatalogDefinition",
    "SetupTemplateMetadata",
]
