"""Settings-driven Streamlit screen definition catalog."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from werewolf_agent.adapters.resources import load_streamlit_screens
from werewolf_agent.clients.streamlit.messages import (
    message_streamlit_screen_column_count_between,
    message_streamlit_screen_definition_invalid,
    message_streamlit_screen_duplicate_element,
    message_streamlit_screen_duplicate_order,
    message_streamlit_screen_invalid_columns,
    message_streamlit_screen_missing_layout,
    message_streamlit_screen_unknown_element,
    message_streamlit_screen_unknown_region,
)
from werewolf_agent.contracts import ConfigError
from werewolf_agent.settings import AppSettings

ScreenId = Literal["sidebar", "setup", "settings", "game"]
RegionId = Literal["main", "summary", "action", "tabs", "top", "side", "bottom"]
ScreenElementId = Literal[
    "brand",
    "history_selector",
    "navigation",
    "header",
    "preset",
    "scenario",
    "narration",
    "agent_strategy",
    "seed",
    "role_counts",
    "character_assignments",
    "local_rules",
    "summary_metrics",
    "validation_messages",
    "manual_seat",
    "setup_summary",
    "submit",
    "preferences",
    "role_definitions",
    "character_definitions",
    "status_bar",
    "game_table",
    "timeline",
    "next_actions",
    "hand_panel",
    "observer_log",
    "observation",
    "advance_job",
    "action_form",
    "auto_advance",
    "observation_memo",
]
ElementVariant = Literal["", "desktop", "mobile"]
ColumnGap = Literal["small", "medium", "large"]

SCREEN_IDS: Final[tuple[ScreenId, ...]] = ("sidebar", "setup", "settings", "game")
MIN_LAYOUT_COLUMNS: Final = 1
MAX_LAYOUT_COLUMNS: Final = 6
MIN_SEED_COLUMNS: Final = 2
MAX_SEED_COLUMNS: Final = 4
MIN_NEXT_ACTION_COLUMNS: Final = 4
MAX_NEXT_ACTION_COLUMNS: Final = 6
GAME_MAIN_COLUMN_COUNT: Final = 2

_ALLOWED_REGIONS: Final[Mapping[str, frozenset[str]]] = {
    "sidebar": frozenset({"main"}),
    "setup": frozenset({"main", "summary", "action"}),
    "settings": frozenset({"tabs"}),
    "game": frozenset({"top", "main", "side", "bottom"}),
}
_ALLOWED_ELEMENTS: Final[Mapping[tuple[str, str], frozenset[str]]] = {
    ("sidebar", "main"): frozenset({"brand", "history_selector", "navigation"}),
    ("setup", "main"): frozenset(
        {
            "header",
            "preset",
            "scenario",
            "narration",
            "agent_strategy",
            "seed",
            "role_counts",
            "character_assignments",
            "local_rules",
        }
    ),
    ("setup", "summary"): frozenset(
        {
            "summary_metrics",
            "validation_messages",
            "manual_seat",
            "setup_summary",
        }
    ),
    ("setup", "action"): frozenset({"submit"}),
    ("settings", "tabs"): frozenset(
        {
            "preferences",
            "role_definitions",
            "character_definitions",
        }
    ),
    ("game", "top"): frozenset({"status_bar"}),
    ("game", "main"): frozenset({"game_table", "timeline", "next_actions"}),
    ("game", "side"): frozenset(
        {
            "hand_panel",
            "observer_log",
            "observation",
            "advance_job",
            "action_form",
            "auto_advance",
            "observation_memo",
        }
    ),
    ("game", "bottom"): frozenset({"timeline"}),
}
_ALLOWED_VARIANTS: Final[Mapping[tuple[str, str, str], frozenset[str]]] = {
    ("game", "main", "timeline"): frozenset({"desktop"}),
    ("game", "bottom", "timeline"): frozenset({"mobile"}),
}


class ScreenElement(BaseModel):
    """One renderable Streamlit screen element."""

    id: ScreenElementId
    order: int = Field(ge=0)
    enabled: bool = True
    variant: ElementVariant = ""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ScreenRegion(BaseModel):
    """A named Streamlit screen region."""

    elements: tuple[ScreenElement, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)


class ScreenLayout(BaseModel):
    """Layout settings for a Streamlit screen."""

    columns: tuple[float, ...] = ()
    gap: ColumnGap = "medium"
    summary_columns: int | None = None
    seed_columns: int | None = None
    next_action_columns: int | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class ScreenDefinition(BaseModel):
    """Definition for one Streamlit screen."""

    layout: ScreenLayout = Field(default_factory=ScreenLayout)
    regions: Mapping[str, ScreenRegion]

    model_config = ConfigDict(extra="forbid", frozen=True)


class ScreenCatalog(BaseModel):
    """Validated Streamlit screen definition catalog."""

    sidebar: ScreenDefinition
    setup: ScreenDefinition
    settings: ScreenDefinition
    game: ScreenDefinition

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_screen_catalog(self) -> ScreenCatalog:
        """Validate region, element, order, and layout contracts."""
        for screen_id in SCREEN_IDS:
            definition = self.screen(screen_id)
            _validate_regions(screen_id, definition)
            _validate_layout(screen_id, definition.layout)
        return self

    def screen(self, screen_id: ScreenId) -> ScreenDefinition:
        """Return one screen definition."""
        return cast(ScreenDefinition, getattr(self, screen_id))

    def layout(self, screen_id: ScreenId) -> ScreenLayout:
        """Return one screen layout definition."""
        return self.screen(screen_id).layout

    def elements(self, screen_id: ScreenId, region_id: RegionId) -> tuple[ScreenElement, ...]:
        """Return enabled elements in render order for one region."""
        region = self.screen(screen_id).regions.get(region_id)
        if region is None:
            return ()
        return tuple(sorted((item for item in region.elements if item.enabled), key=_sort_element))

    def element_enabled(
        self,
        screen_id: ScreenId,
        region_id: RegionId,
        element_id: ScreenElementId,
        *,
        variant: ElementVariant = "",
    ) -> bool:
        """Return whether one element is enabled in a region."""
        return any(
            element.id == element_id and element.variant == variant
            for element in self.elements(screen_id, region_id)
        )


def load_screen_catalog(settings: AppSettings) -> ScreenCatalog:
    """Load and validate the Streamlit screen definition catalog."""
    payload = load_streamlit_screens(settings.streamlit_screens_path)
    try:
        return ScreenCatalog.model_validate(payload)
    except ValidationError as exc:
        raise ConfigError(message_streamlit_screen_definition_invalid(exc)) from exc


def _sort_element(element: ScreenElement) -> tuple[int, str, str]:
    return (element.order, element.id, element.variant)


def _validate_regions(screen_id: str, definition: ScreenDefinition) -> None:
    allowed_regions = _ALLOWED_REGIONS[screen_id]
    for region_id, region in definition.regions.items():
        if region_id not in allowed_regions:
            raise ValueError(message_streamlit_screen_unknown_region(screen_id, region_id))
        _validate_region_elements(screen_id, region_id, region)


def _validate_region_elements(screen_id: str, region_id: str, region: ScreenRegion) -> None:
    allowed_elements = _ALLOWED_ELEMENTS[(screen_id, region_id)]
    seen_orders: set[int] = set()
    seen_elements: set[tuple[str, str]] = set()
    for element in region.elements:
        if element.id not in allowed_elements:
            raise ValueError(
                message_streamlit_screen_unknown_element(screen_id, region_id, element.id)
            )
        _validate_element_variant(screen_id, region_id, element)
        if element.order in seen_orders:
            raise ValueError(
                message_streamlit_screen_duplicate_order(screen_id, region_id, element.order)
            )
        seen_orders.add(element.order)
        element_key = (element.id, element.variant)
        if element_key in seen_elements:
            raise ValueError(
                message_streamlit_screen_duplicate_element(
                    screen_id,
                    region_id,
                    element.id,
                    element.variant,
                )
            )
        seen_elements.add(element_key)


def _validate_element_variant(screen_id: str, region_id: str, element: ScreenElement) -> None:
    allowed_variants = _ALLOWED_VARIANTS.get((screen_id, region_id, element.id), frozenset({""}))
    if element.variant not in allowed_variants:
        raise ValueError(message_streamlit_screen_unknown_element(screen_id, region_id, element.id))


def _validate_layout(screen_id: str, layout: ScreenLayout) -> None:
    if screen_id == "setup":
        _validate_required_column_count(
            screen_id,
            "summary_columns",
            layout.summary_columns,
            MIN_LAYOUT_COLUMNS,
            MAX_LAYOUT_COLUMNS,
        )
        _validate_required_column_count(
            screen_id,
            "seed_columns",
            layout.seed_columns,
            MIN_SEED_COLUMNS,
            MAX_SEED_COLUMNS,
        )
    if screen_id == "game":
        if len(layout.columns) != GAME_MAIN_COLUMN_COUNT or any(
            value <= 0 for value in layout.columns
        ):
            raise ValueError(message_streamlit_screen_invalid_columns(screen_id))
        _validate_required_column_count(
            screen_id,
            "next_action_columns",
            layout.next_action_columns,
            MIN_NEXT_ACTION_COLUMNS,
            MAX_NEXT_ACTION_COLUMNS,
        )


def _validate_required_column_count(
    screen_id: str,
    field_name: str,
    value: int | None,
    minimum: int,
    maximum: int,
) -> None:
    if value is None:
        raise ValueError(message_streamlit_screen_missing_layout(screen_id, field_name))
    if not minimum <= value <= maximum:
        raise ValueError(
            message_streamlit_screen_column_count_between(field_name, minimum, maximum)
        )
