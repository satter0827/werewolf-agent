from pathlib import Path

from werewolf_agent.interface.entrypoint.streamlit.i18n import (
    current_language,
    label_key_sets,
    load_i18n,
    message_key_sets,
    remember_language,
)
from werewolf_agent.interface.runtime import AppSettings


def test_i18n_catalog_has_matching_ja_en_keys() -> None:
    catalog = load_i18n(AppSettings(_env_file=None))

    assert message_key_sets(catalog)["ja"] == message_key_sets(catalog)["en"]
    assert label_key_sets(catalog)["ja"] == label_key_sets(catalog)["en"]
    assert catalog.t("ja", "nav.play") == "プレイ"
    assert catalog.t("en", "nav.play") == "Play"


def test_language_state_defaults_to_settings_then_session_wins() -> None:
    session: dict[str, object] = {}
    settings = AppSettings(_env_file=None, streamlit_language="ja")

    assert current_language(session, settings) == "ja"
    remember_language(session, "en")
    assert current_language(session, settings) == "en"


def test_i18n_catalog_can_be_overridden_by_settings_file(tmp_path: Path) -> None:
    i18n_file = tmp_path / "i18n.toml"
    i18n_file.write_text(
        """
[languages]
ja = "日本語"
en = "English"

[messages.en]
hello = "Hello {name}"

[messages.ja]
hello = "こんにちは {name}"

[labels.en.role]
villager = "Villager"

[labels.ja.role]
villager = "村人"
""".strip(),
        encoding="utf-8",
    )
    settings = AppSettings(_env_file=None, streamlit_i18n_file=str(i18n_file))

    catalog = load_i18n(settings)

    assert catalog.t("ja", "hello", name="葵") == "こんにちは 葵"
    assert catalog.label("en", "role", "villager") == "Villager"
