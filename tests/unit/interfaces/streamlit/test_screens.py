from pathlib import Path

import pytest

from werewolf_agent.configuration import AppSettings
from werewolf_agent.contracts import ConfigError
from werewolf_agent.interfaces.streamlit.screens import load_screen_catalog


def test_packaged_screen_catalog_controls_regions() -> None:
    catalog = load_screen_catalog(AppSettings(_env_file=None))

    assert catalog.layout("game").columns == (1.55, 1.0)
    assert catalog.layout("game").next_action_columns == 4
    assert [element.id for element in catalog.elements("sidebar", "main")] == [
        "brand",
        "history_selector",
        "navigation",
    ]
    assert [element.id for element in catalog.elements("game", "side")] == [
        "hand_panel",
        "observer_log",
        "observation",
        "advance_job",
        "action_form",
        "auto_advance",
        "observation_memo",
    ]
    assert catalog.element_enabled("game", "main", "timeline", variant="desktop")
    assert catalog.element_enabled("game", "bottom", "timeline", variant="mobile")


def test_screen_catalog_can_be_overridden_by_settings_file(tmp_path: Path) -> None:
    screens_file = tmp_path / "screens.toml"
    screens_file.write_text(_screen_definition(sidebar_brand_enabled=False), encoding="utf-8")
    settings = AppSettings(_env_file=None, streamlit_screens_file=str(screens_file))

    catalog = load_screen_catalog(settings)

    assert [element.id for element in catalog.elements("sidebar", "main")] == [
        "history_selector",
        "navigation",
    ]
    assert not catalog.element_enabled("sidebar", "main", "brand")


def test_screen_catalog_rejects_unknown_element(tmp_path: Path) -> None:
    screens_file = tmp_path / "screens.toml"
    screens_file.write_text(
        _screen_definition(sidebar_extra_element="unknown"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="streamlit screen definition is invalid"):
        load_screen_catalog(AppSettings(_env_file=None, streamlit_screens_file=str(screens_file)))


def test_screen_catalog_rejects_duplicate_order(tmp_path: Path) -> None:
    screens_file = tmp_path / "screens.toml"
    screens_file.write_text(_screen_definition(duplicate_sidebar_order=True), encoding="utf-8")

    with pytest.raises(ConfigError, match="duplicate order"):
        load_screen_catalog(AppSettings(_env_file=None, streamlit_screens_file=str(screens_file)))


def test_screen_catalog_rejects_invalid_column_ratios(tmp_path: Path) -> None:
    screens_file = tmp_path / "screens.toml"
    screens_file.write_text(_screen_definition(game_columns="0, 1.0"), encoding="utf-8")

    with pytest.raises(ConfigError, match="column ratios"):
        load_screen_catalog(AppSettings(_env_file=None, streamlit_screens_file=str(screens_file)))


def _screen_definition(
    *,
    sidebar_brand_enabled: bool = True,
    sidebar_extra_element: str | None = None,
    duplicate_sidebar_order: bool = False,
    game_columns: str = "1.55, 1.0",
) -> str:
    brand_enabled = str(sidebar_brand_enabled).lower()
    history_order = 10 if duplicate_sidebar_order else 20
    extra = (
        f"""
[[sidebar.regions.main.elements]]
id = "{sidebar_extra_element}"
order = 40
enabled = true
"""
        if sidebar_extra_element is not None
        else ""
    )
    return f"""
[sidebar.regions.main]
[[sidebar.regions.main.elements]]
id = "brand"
order = 10
enabled = {brand_enabled}

[[sidebar.regions.main.elements]]
id = "history_selector"
order = {history_order}
enabled = true

[[sidebar.regions.main.elements]]
id = "navigation"
order = 30
enabled = true
{extra}
[setup.layout]
summary_columns = 3
seed_columns = 2

[setup.regions.main]
elements = []

[setup.regions.summary]
elements = []

[setup.regions.action]
elements = []

[settings.regions.tabs]
elements = []

[game.layout]
columns = [{game_columns}]
gap = "medium"
next_action_columns = 4

[game.regions.top]
elements = []

[game.regions.main]
elements = []

[game.regions.side]
elements = []

[game.regions.bottom]
elements = []
""".strip()
