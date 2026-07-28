"""品質runnerが扱うGit差分とsnapshotを検査する。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.quality.repository import capture_snapshot, resolve_changes


def test_change_set_combines_commits_workspace_and_untracked_files(tmp_path: Path) -> None:
    """cleanなCI差分とローカル差分を同じ変更集合へ統合する。"""
    _initialize_repository(tmp_path)
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "committed.txt").write_text("committed\n", encoding="utf-8")
    _git(tmp_path, "add", "committed.txt")
    _git(tmp_path, "commit", "-m", "committed")
    (tmp_path / "tracked.txt").write_text("workspace\n", encoding="utf-8")
    (tmp_path / "untracked.txt").write_text("untracked\n", encoding="utf-8")

    change = resolve_changes(base, "HEAD", root=tmp_path)

    assert change.base_revision == base
    assert change.merge_base_revision == base
    assert change.changed_paths == ("committed.txt", "tracked.txt", "untracked.txt")


def test_snapshot_tracks_source_changes_but_ignores_declared_artifacts(tmp_path: Path) -> None:
    """品質成果物を除外し、sourceの未追跡変更だけをfingerprintへ含める。"""
    _initialize_repository(tmp_path)
    initial = capture_snapshot(root=tmp_path)
    generated = tmp_path / ".werewolf-agent" / "quality" / "report.json"
    generated.parent.mkdir(parents=True)
    generated.write_text("{}", encoding="utf-8")

    assert capture_snapshot(root=tmp_path) == initial

    (tmp_path / "source.py").write_text("value = 1\n", encoding="utf-8")
    changed = capture_snapshot(root=tmp_path)

    assert changed.dirty is True
    assert changed.fingerprint != initial.fingerprint


def _initialize_repository(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.email", "quality@example.invalid")
    _git(root, "config", "user.name", "Quality Test")
    (root / ".gitignore").write_text(".werewolf-agent/\n", encoding="utf-8")
    (root / "tracked.txt").write_text("initial\n", encoding="utf-8")
    _git(root, "add", ".gitignore", "tracked.txt")
    _git(root, "commit", "-m", "initial")


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()
