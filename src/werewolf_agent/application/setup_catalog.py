"""同梱する完全なsetup templateのread-only catalogを定義する。"""

from __future__ import annotations

from typing import Self

from pydantic import ConfigDict, field_validator, model_validator

from werewolf_agent.application.models.base import ApplicationModel
from werewolf_agent.application.setup_document import GameSetupDocument
from werewolf_agent.application.validation import non_blank


class SetupTemplateMetadata(ApplicationModel):
    """一つの同梱templateに関する公開metadataを表す。"""

    name: str
    summary: str
    file: str

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("name", "summary", "file")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """空でないtemplate metadata textを返す。"""
        return non_blank(value, "template metadata")


class SetupTemplateCatalogDefinition(ApplicationModel):
    """Template文書を読み込む前のcatalog resourceを表す。"""

    recommended_template_id: str
    template_order: tuple[str, ...]
    templates: dict[str, SetupTemplateMetadata]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """Catalog内の全templateに明示的な順序を要求する。"""
        if set(self.template_order) != set(self.templates):
            raise ValueError("template_order must contain every template exactly once")
        if self.recommended_template_id not in self.templates:
            raise ValueError("recommended_template_id must reference a template")
        return self


class SetupTemplateCatalog(ApplicationModel):
    """Applicationが使用できる検証済み同梱templateを保持する。"""

    recommended_template_id: str
    template_order: tuple[str, ...]
    metadata: dict[str, SetupTemplateMetadata]
    documents: dict[str, GameSetupDocument]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_documents(self) -> Self:
        """順序付けた全templateにmetadataと文書を要求する。"""
        if set(self.metadata) != set(self.documents) or set(self.template_order) != set(
            self.documents
        ):
            raise ValueError("template metadata and documents must have identical IDs")
        return self

    def require_document(self, template_id: str) -> GameSetupDocument:
        """一つの完全なtemplateを返し、不存在時はfallbackせず失敗する。"""
        return self.documents[non_blank(template_id, "template_id")]


__all__ = [
    "SetupTemplateCatalog",
    "SetupTemplateCatalogDefinition",
    "SetupTemplateMetadata",
]
