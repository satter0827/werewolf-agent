"""配布物の公開契約を検査する。"""

from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.serial
def test_wheel_contains_entrypoints_and_packaged_resources() -> None:
    """wheelへCLI entrypointと実行時resourceを含める。"""

    wheels = list((ROOT / ".werewolf-agent" / "outputs" / "package").glob("*.whl"))
    assert len(wheels) == 1, "先にcheck profileで配布物を構築してください。"

    with ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())
        entry_points = next(name for name in names if name.endswith(".dist-info/entry_points.txt"))
        metadata = wheel.read(entry_points).decode("utf-8")

    assert "werewolf-agent =" in metadata
    assert "werewolf-agent-api =" in metadata
    assert "werewolf-agent-worker =" in metadata
    assert "werewolf_agent/settings/resources/defaults.toml" in names
    assert "werewolf_agent/agents/resources/prompts/agent_decision.toml" in names
