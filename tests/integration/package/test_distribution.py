"""配布物の公開契約を検査する。"""

from pathlib import Path
from tarfile import open as open_tar
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
        package_metadata = next(name for name in names if name.endswith(".dist-info/METADATA"))
        entrypoint_text = wheel.read(entry_points).decode("utf-8")
        metadata_text = wheel.read(package_metadata).decode("utf-8")

    assert "werewolf-agent =" in entrypoint_text
    assert "werewolf-agent-api =" in entrypoint_text
    assert "werewolf-agent-worker =" in entrypoint_text
    assert "werewolf_agent/settings/resources/defaults.toml" in names
    assert "werewolf_agent/adapters/llm/resources/agent_decision.toml" in names
    assert not any("notebooks/" in name for name in names)
    assert (
        "Summary: Deterministic headless Werewolf SDK for agent experiments and applications."
    ) in metadata_text
    assert "Keywords: ai-agents,llm,multi-agent-systems,social-deduction,werewolf" in metadata_text
    requires_dist = [
        line.removeprefix("Requires-Dist: ")
        for line in metadata_text.splitlines()
        if line.startswith("Requires-Dist: ")
    ]
    assert requires_dist
    assert all("extra ==" in requirement for requirement in requires_dist)
    for extra in ("application", "api", "cli", "llm", "streamlit", "worker"):
        assert f"Provides-Extra: {extra}" in metadata_text
    for label, url in (
        ("Homepage", "https://github.com/satter0827/werewolf-agent"),
        ("Documentation", "https://github.com/satter0827/werewolf-agent/tree/main/docs"),
        ("Repository", "https://github.com/satter0827/werewolf-agent"),
        ("Issues", "https://github.com/satter0827/werewolf-agent/issues"),
    ):
        assert f"Project-URL: {label}, {url}" in metadata_text


@pytest.mark.serial
def test_sdist_excludes_repository_notebooks() -> None:
    """リポジトリ向けNotebookを製品source distributionへ混入させない。"""
    archives = list((ROOT / ".werewolf-agent" / "outputs" / "package").glob("*.tar.gz"))
    assert len(archives) == 1, "先にcheck profileで配布物を構築してください。"

    with open_tar(archives[0], "r:gz") as archive:
        names = archive.getnames()

    assert not any("/notebooks/" in name for name in names)
