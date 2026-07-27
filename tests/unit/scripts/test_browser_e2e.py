from pathlib import Path

from PIL import Image
from scripts.browser.e2e import create_contact_sheet


def test_contact_sheet_uses_two_columns_and_keeps_labels(tmp_path: Path) -> None:
    for index in range(3):
        Image.new("RGB", (1280, 720), (index * 20, 40, 60)).save(
            tmp_path / f"meaningful-state-{index}.png"
        )

    target = create_contact_sheet(tmp_path)

    assert target == tmp_path / "contact-sheet.png"
    with Image.open(target) as sheet:
        assert sheet.width == 1040
        assert sheet.height == 1120
