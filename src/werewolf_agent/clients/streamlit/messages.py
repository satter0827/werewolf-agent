"""clients streamlit messagesが所有する文言."""

from __future__ import annotations


def message_field_must_be_toml_table(field_name: str) -> str:
    """Return a TOML table validation message."""
    return f"{field_name} must be a TOML table"


def message_field_must_be_non_empty_string(field_name: str) -> str:
    """Return a non-empty string validation message."""
    return f"{field_name} must be a non-empty string"


def message_localized_keys_must_match_en(
    field_name: str,
    lang: str,
    *,
    missing: str,
    extra: str,
) -> str:
    """Return a localized message-key coverage validation message."""
    return f"{field_name}.{lang} keys must match en: missing={missing} extra={extra}"


def message_localized_label_kinds_must_match_en(lang: str) -> str:
    """Return a localized label-kind coverage validation message."""
    return f"labels.{lang} kinds must match en"


def message_streamlit_screen_definition_invalid(error: object) -> str:
    """Return a Streamlit screen-definition validation message."""
    return f"streamlit screen definition is invalid: {error}"


def message_streamlit_screen_unknown_region(screen_id: str, region_id: str) -> str:
    """Return an unknown Streamlit screen region message."""
    return f"streamlit screen {screen_id} has unknown region: {region_id}"


def message_streamlit_screen_unknown_element(
    screen_id: str,
    region_id: str,
    element_id: str,
) -> str:
    """Return an unknown Streamlit screen element message."""
    return f"streamlit screen {screen_id}.{region_id} has unknown element: {element_id}"


def message_streamlit_screen_duplicate_order(
    screen_id: str,
    region_id: str,
    order: int,
) -> str:
    """Return a duplicate Streamlit screen order message."""
    return f"streamlit screen {screen_id}.{region_id} has duplicate order: {order}"


def message_streamlit_screen_duplicate_element(
    screen_id: str,
    region_id: str,
    element_id: str,
    variant: str,
) -> str:
    """Return a duplicate Streamlit screen element message."""
    suffix = f":{variant}" if variant else ""
    return f"streamlit screen {screen_id}.{region_id} has duplicate element: {element_id}{suffix}"


def message_streamlit_screen_invalid_columns(screen_id: str) -> str:
    """Return an invalid Streamlit screen column-ratio message."""
    return f"streamlit screen {screen_id} column ratios must be positive"


def message_streamlit_screen_column_count_between(
    field_name: str,
    minimum: int,
    maximum: int,
) -> str:
    """Return a Streamlit screen column-count validation message."""
    return f"{field_name} must be between {minimum} and {maximum}"


def message_streamlit_screen_missing_layout(screen_id: str, field_name: str) -> str:
    """Return a missing Streamlit screen layout setting message."""
    return f"streamlit screen {screen_id} must define layout.{field_name}"
