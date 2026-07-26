from pathlib import Path

from werewolf_agent.adapters.resources import (
    STREAMLIT_PACKAGE,
    STREAMLIT_SCREENS_FILE,
    load_packaged_text,
)
from werewolf_agent.clients.streamlit.screens import load_screen_catalog
from werewolf_agent.settings import AppSettings


def test_packaged_screen_catalog_controls_regions() -> None:
    catalog = load_screen_catalog(AppSettings(_env_file=None))

    assert catalog.workspace_order == ("play", "observe", "records", "admin", "preferences")
    assert catalog.layout("game").columns == (1.55, 1.0)
    assert [element.id for element in catalog.elements("sidebar", "main")] == [
        "brand",
        "history_selector",
        "navigation",
    ]
    assert catalog.element_enabled("game", "main", "timeline", variant="desktop")
    assert catalog.element_enabled("game", "bottom", "timeline", variant="mobile")


def test_valid_override_applies_workspace_and_global_display_settings(tmp_path: Path) -> None:
    screens_file = tmp_path / "screens.toml"
    bundled = load_packaged_text(STREAMLIT_PACKAGE, STREAMLIT_SCREENS_FILE)
    screens_file.write_text(
        bundled.replace(
            'workspace_order = ["play", "observe", "records", "admin", "preferences"]',
            'workspace_order = ["records", "play", "observe", "preferences", "admin"]',
        )
        .replace('information_density = "comfortable"', 'information_density = "compact"')
        .replace("analysis_collapsed = true", "analysis_collapsed = false"),
        encoding="utf-8",
    )

    catalog = load_screen_catalog(
        AppSettings(_env_file=None, streamlit_screens_file=str(screens_file))
    )

    assert catalog.workspace_order == (
        "records",
        "play",
        "observe",
        "preferences",
        "admin",
    )
    assert catalog.information_density == "compact"
    assert catalog.analysis_collapsed is False


def test_incomplete_override_falls_back_to_required_bundled_elements(tmp_path: Path) -> None:
    screens_file = tmp_path / "screens.toml"
    screens_file.write_text(_screen_definition(brand_order=25), encoding="utf-8")

    catalog = load_screen_catalog(
        AppSettings(_env_file=None, streamlit_screens_file=str(screens_file))
    )

    assert [element.id for element in catalog.elements("sidebar", "main")] == [
        "brand",
        "history_selector",
        "navigation",
    ]


def test_invalid_unknown_element_falls_back_to_bundled_catalog(tmp_path: Path) -> None:
    screens_file = tmp_path / "screens.toml"
    screens_file.write_text(_screen_definition(extra_element="unknown"), encoding="utf-8")

    catalog = load_screen_catalog(
        AppSettings(_env_file=None, streamlit_screens_file=str(screens_file))
    )

    assert catalog.workspace_order == ("play", "observe", "records", "admin", "preferences")


def test_duplicate_order_falls_back_to_bundled_catalog(tmp_path: Path) -> None:
    screens_file = tmp_path / "screens.toml"
    screens_file.write_text(_screen_definition(history_order=10), encoding="utf-8")

    catalog = load_screen_catalog(
        AppSettings(_env_file=None, streamlit_screens_file=str(screens_file))
    )

    assert catalog.layout("game").columns == (1.55, 1.0)


def test_invalid_column_ratios_fall_back_to_bundled_catalog(tmp_path: Path) -> None:
    screens_file = tmp_path / "screens.toml"
    screens_file.write_text(_screen_definition(game_columns="0, 1.0"), encoding="utf-8")

    catalog = load_screen_catalog(
        AppSettings(_env_file=None, streamlit_screens_file=str(screens_file))
    )

    assert catalog.layout("game").columns == (1.55, 1.0)


def _screen_definition(
    *,
    brand_order: int = 10,
    history_order: int = 20,
    extra_element: str | None = None,
    game_columns: str = "1.55, 1.0",
) -> str:
    extra = (
        f'\n[[sidebar.regions.main.elements]]\nid = "{extra_element}"\norder = 40\n'
        if extra_element is not None
        else ""
    )
    return f"""
workspace_order = ["play", "observe", "records", "admin", "preferences"]
information_density = "comfortable"
analysis_collapsed = true

[sidebar.regions.main]
[[sidebar.regions.main.elements]]
id = "brand"
order = {brand_order}

[[sidebar.regions.main.elements]]
id = "history_selector"
order = {history_order}

[[sidebar.regions.main.elements]]
id = "navigation"
order = 30
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
