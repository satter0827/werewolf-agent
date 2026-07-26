from pathlib import Path

from scripts._infra import node


def test_node_executable_prefers_required_major(monkeypatch, tmp_path: Path) -> None:
    unsupported = tmp_path / "unsupported" / "node.exe"
    supported = tmp_path / "supported" / "node.exe"
    unsupported.parent.mkdir()
    supported.parent.mkdir()
    unsupported.touch()
    supported.touch()
    monkeypatch.setattr(
        node,
        "_candidate_nodes",
        lambda _fallback: (unsupported, supported),
    )
    monkeypatch.setattr(
        node,
        "_major_version",
        lambda executable: 22 if executable == supported else 24,
    )

    assert node.node_executable() == str(supported)


def test_npm_executable_uses_selected_node_directory(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "node.exe"
    npm = tmp_path / "npm.cmd"
    executable.touch()
    npm.touch()
    monkeypatch.setattr(node, "node_executable", lambda: str(executable))

    assert node.npm_executable() == str(npm)


def test_preferred_node_directory_rejects_other_major(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "node.exe"
    executable.touch()
    monkeypatch.setattr(node, "node_executable", lambda: str(executable))
    monkeypatch.setattr(node, "_major_version", lambda _executable: 24)

    assert node.preferred_node_directory() is None
