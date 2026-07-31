from pathlib import Path

from werewolf_agent.clients.streamlit.i18n import (
    label_key_sets,
    load_i18n,
    message_key_sets,
)
from werewolf_agent.clients.streamlit.preferences import preferred_language, remember_language
from werewolf_agent.settings import AppSettings


def test_i18n_catalog_has_matching_ja_en_keys() -> None:
    catalog = load_i18n(AppSettings(_env_file=None))

    assert message_key_sets(catalog)["ja"] == message_key_sets(catalog)["en"]
    assert label_key_sets(catalog)["ja"] == label_key_sets(catalog)["en"]
    assert catalog.t("ja", "nav.play") == "プレイ"
    assert catalog.t("en", "nav.play") == "Play"
    assert catalog.t("ja", "history.column.day") == "日"
    assert catalog.t("ja", "result.fact.finish_day", day=5) == "5日目で終了しました。"


def test_language_state_defaults_to_settings_then_session_wins() -> None:
    session: dict[str, object] = {}
    settings = AppSettings(_env_file=None, streamlit_language="ja")

    assert preferred_language(session, settings.streamlit_language) == "ja"
    remember_language(session, "en")
    assert preferred_language(session, settings.streamlit_language) == "en"
    assert session["werewolf_streamlit_preferences"] == {"language": "en"}


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


def test_invalid_i18n_override_falls_back_to_packaged_catalog(tmp_path: Path) -> None:
    i18n_file = tmp_path / "i18n.toml"
    i18n_file.write_text("not = [valid", encoding="utf-8")

    catalog = load_i18n(AppSettings(_env_file=None, streamlit_i18n_file=str(i18n_file)))

    assert catalog.t("ja", "nav.play") == "プレイ"
