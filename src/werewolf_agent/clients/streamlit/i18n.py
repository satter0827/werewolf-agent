"""Settings-driven i18n helpers for the Streamlit UI."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, Final, Literal, cast

from werewolf_agent.adapters.resources import load_streamlit_i18n
from werewolf_agent.clients.streamlit.constants import UNKNOWN_VALUE_LABEL
from werewolf_agent.clients.streamlit.messages import (
    message_field_must_be_non_empty_string,
    message_field_must_be_toml_table,
    message_localized_keys_must_match_en,
    message_localized_label_kinds_must_match_en,
)
from werewolf_agent.clients.streamlit.state import KEY_STREAMLIT_PREFERENCES
from werewolf_agent.contracts import ConfigError
from werewolf_agent.settings import AppSettings

Language = Literal["ja", "en"]
SUPPORTED_LANGUAGES: Final[frozenset[Language]] = frozenset({"ja", "en"})


@dataclass(frozen=True)
class I18nCatalog:
    """Loaded Streamlit UI translations."""

    languages: Mapping[Language, str]
    messages: Mapping[Language, Mapping[str, str]]
    labels: Mapping[Language, Mapping[str, Mapping[str, str]]]

    def t(self, lang: Language, key: str, **values: object) -> str:
        """Translate a message key and format optional values."""
        template = self.messages.get(lang, self.messages["ja"]).get(
            key,
            self.messages["en"].get(key, key),
        )
        return template.format(**values) if values else template

    def label(self, lang: Language, kind: str, value: object) -> str:
        """Return a translated label for a stable game identifier."""
        text = str(value or "")
        if kind == "winner" and not text:
            text = UNKNOWN_VALUE_LABEL
        if not text:
            return self.t(lang, "common.unknown")
        return (
            self.labels.get(lang, self.labels["ja"])
            .get(kind, {})
            .get(
                text,
                text.replace("_", " ").title() if lang == "en" else text,
            )
        )


def load_i18n(settings: AppSettings) -> I18nCatalog:
    """Load the Streamlit translation catalog from settings."""
    payload = load_streamlit_i18n(settings.streamlit_i18n_path)
    return _catalog_from_payload(payload)


def current_language(session: MutableMapping[str, Any], settings: AppSettings) -> Language:
    """Return the current UI language, defaulting to settings only on first load."""
    preferences = session.get(KEY_STREAMLIT_PREFERENCES)
    raw_value = (
        preferences.get("language", settings.streamlit_language)
        if isinstance(preferences, dict)
        else settings.streamlit_language
    )
    return normalize_language(raw_value)


def remember_language(session: MutableMapping[str, Any], language: str) -> None:
    """Store the current UI language in Streamlit session state."""
    preferences = session.get(KEY_STREAMLIT_PREFERENCES)
    next_preferences = dict(preferences) if isinstance(preferences, dict) else {}
    next_preferences["language"] = normalize_language(language)
    session[KEY_STREAMLIT_PREFERENCES] = next_preferences


def normalize_language(value: object) -> Language:
    """Return a supported language code."""
    candidate = str(value).strip().lower()
    return candidate if candidate in SUPPORTED_LANGUAGES else "ja"


def message_key_sets(catalog: I18nCatalog) -> Mapping[Language, frozenset[str]]:
    """Return message-key sets for tests."""
    return {lang: frozenset(messages) for lang, messages in catalog.messages.items()}


def label_key_sets(catalog: I18nCatalog) -> Mapping[Language, Mapping[str, frozenset[str]]]:
    """Return label-key sets for tests."""
    return {
        lang: {kind: frozenset(values) for kind, values in kinds.items()}
        for lang, kinds in catalog.labels.items()
    }


def _catalog_from_payload(payload: Mapping[str, object]) -> I18nCatalog:
    languages = _language_names(payload.get("languages"))
    messages = _localized_text_maps(payload.get("messages"), field_name="messages")
    labels = _localized_label_maps(payload.get("labels"))
    _validate_complete_keys(messages, field_name="messages")
    _validate_complete_label_keys(labels)
    return I18nCatalog(languages=languages, messages=messages, labels=labels)


def _language_names(value: object) -> dict[Language, str]:
    names = _as_mapping(value, field_name="languages")
    result = {lang: _required_text(names.get(lang), f"languages.{lang}") for lang in ("ja", "en")}
    return cast(dict[Language, str], result)


def _localized_text_maps(value: object, *, field_name: str) -> dict[Language, dict[str, str]]:
    mapping = _as_mapping(value, field_name=field_name)
    result = {
        lang: _text_map(mapping.get(lang), field_name=f"{field_name}.{lang}")
        for lang in ("ja", "en")
    }
    return cast(dict[Language, dict[str, str]], result)


def _localized_label_maps(value: object) -> dict[Language, dict[str, dict[str, str]]]:
    mapping = _as_mapping(value, field_name="labels")
    result: dict[str, dict[str, dict[str, str]]] = {}
    for lang in ("ja", "en"):
        language_labels = _as_mapping(mapping.get(lang), field_name=f"labels.{lang}")
        result[lang] = {
            str(kind): _text_map(values, field_name=f"labels.{lang}.{kind}")
            for kind, values in language_labels.items()
        }
    return cast(dict[Language, dict[str, dict[str, str]]], result)


def _text_map(value: object, *, field_name: str) -> dict[str, str]:
    mapping = _as_mapping(value, field_name=field_name)
    return {str(key): _required_text(item, f"{field_name}.{key}") for key, item in mapping.items()}


def _as_mapping(value: object, *, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ConfigError(message_field_must_be_toml_table(field_name))
    return {str(key): item for key, item in value.items()}


def _required_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ConfigError(message_field_must_be_non_empty_string(field_name))
    return text


def _validate_complete_keys(
    localized_maps: Mapping[Language, Mapping[str, str]],
    *,
    field_name: str,
) -> None:
    expected = set(localized_maps["en"])
    for lang, values in localized_maps.items():
        missing = sorted(expected - set(values))
        extra = sorted(set(values) - expected)
        if missing or extra:
            raise ConfigError(
                message_localized_keys_must_match_en(
                    field_name,
                    lang,
                    missing=",".join(missing),
                    extra=",".join(extra),
                )
            )


def _validate_complete_label_keys(
    localized_labels: Mapping[Language, Mapping[str, Mapping[str, str]]],
) -> None:
    expected_kinds = set(localized_labels["en"])
    for lang, labels in localized_labels.items():
        if set(labels) != expected_kinds:
            raise ConfigError(message_localized_label_kinds_must_match_en(lang))
        for kind, values in labels.items():
            _validate_complete_keys(
                {"en": localized_labels["en"][kind], lang: values},
                field_name=f"labels.{lang}.{kind}",
            )
