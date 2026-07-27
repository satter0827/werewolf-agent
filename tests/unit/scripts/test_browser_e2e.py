import ast
from pathlib import Path

import pytest
from PIL import Image
from scripts.browser.catalog import capture_filenames, load_catalog, scenario_expression
from scripts.browser.e2e import _commands, create_contact_sheet


def test_contact_sheet_uses_two_columns_and_keeps_labels(tmp_path: Path) -> None:
    screenshots = tmp_path / "public" / "screenshots"
    screenshots.mkdir(parents=True)
    for index in range(3):
        Image.new("RGB", (1280, 720), (index * 20, 40, 60)).save(
            screenshots / f"meaningful-state-{index}.png"
        )
    private = tmp_path / "private" / "playwright"
    private.mkdir(parents=True)
    for index in range(3):
        Image.new("RGB", (1280, 720), (200, index * 20, 60)).save(private / f"failure-{index}.png")

    target = create_contact_sheet(tmp_path / "public")

    assert target == tmp_path / "public" / "contact-sheet.png"
    with Image.open(target) as sheet:
        assert sheet.width == 1040
        assert sheet.height == 1120


def test_browser_selection_resolves_journey_state_and_device_independently(tmp_path: Path) -> None:
    expression = scenario_expression("play", "finished")
    commands = _commands(tmp_path, scenario_filter=expression)

    assert expression == "test_completed_game_presents_result_before_timeline"
    assert "-k" in commands[-1]
    assert expression in commands[-1]


def test_incompatible_browser_journey_and_state_are_rejected() -> None:
    with pytest.raises(ValueError, match="対応するscenario"):
        scenario_expression("observe", "error")


def test_capture_selects_only_its_scenario_and_device_filenames() -> None:
    expression = scenario_expression(None, None, ("gameplay-complete",))
    filenames = capture_filenames(("gameplay-complete",), ("desktop", "mobile"))

    assert expression == "test_completed_game_presents_result_before_timeline"
    assert filenames == (
        "streamlit-gameplay-complete-desktop.png",
        "streamlit-gameplay-complete-mobile.png",
    )


def test_device_specific_capture_rejects_an_incompatible_device() -> None:
    with pytest.raises(ValueError, match="指定device"):
        capture_filenames(("setup-narrow-320",), ("mobile",))


def test_catalog_scenarios_reference_real_streamlit_tests() -> None:
    """Catalogのjourney・state・captureを存在しないtest名へ向けない。"""
    scenario_path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "browser"
        / "scenarios"
        / "test_streamlit.py"
    )
    functions = {
        node.name
        for node in ast.parse(scenario_path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }
    catalog = load_catalog()
    referenced = {
        name
        for section in ("journeys", "states")
        for values in catalog[section].values()
        for name in values
        if isinstance(name, str)
    }
    referenced.update(
        str(value["scenario"]) for value in catalog["captures"].values() if isinstance(value, dict)
    )

    assert referenced == functions
