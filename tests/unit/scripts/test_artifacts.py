"""成果物のscratch構築と公開契約。"""

from pathlib import Path

import pytest
from scripts._infra import artifacts
from scripts._infra.artifacts import publish_directory, replace_directory, staged_directory


def test_staged_directory_uses_repository_runtime_and_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scratch directoryを指定runtime内に作り、終了時に削除する。"""
    monkeypatch.setattr("scripts._infra.artifacts.TEMPORARY_ROOT", tmp_path)

    with staged_directory("docs") as staging:
        assert staging.parent == tmp_path / "build"
        (staging / "index.html").write_text("ok", encoding="utf-8")

    assert not staging.exists()


def test_publish_directory_replaces_validated_build(tmp_path: Path) -> None:
    """検証済みbuildをdirectory単位で置換する。"""
    target = tmp_path / "build" / "docs"
    target.mkdir(parents=True)
    (target / "old.html").write_text("old", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "index.html").write_text("new", encoding="utf-8")

    publish_directory(staging, target)

    assert (target / "index.html").read_text(encoding="utf-8") == "new"
    assert not (target / "old.html").exists()
    assert not staging.exists()
    assert not target.with_name(".docs.backup").exists()


def test_publish_directory_restores_previous_build_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """公開処理の失敗時に直前の正常buildを復元する。"""
    target = tmp_path / "build" / "docs"
    target.mkdir(parents=True)
    (target / "index.html").write_text("old", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "index.html").write_text("new", encoding="utf-8")
    original_replace = Path.replace

    def fail_staging_replace(path: Path, destination: Path) -> Path:
        if path == staging:
            raise OSError("publish failed")
        return original_replace(path, destination)

    monkeypatch.setattr(Path, "replace", fail_staging_replace)

    with pytest.raises(OSError, match="publish failed"):
        publish_directory(staging, target)

    assert (target / "index.html").read_text(encoding="utf-8") == "old"


def test_replace_directory_retries_transient_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windowsの短時間lockを待って同一filesystem内の公開を完了する。"""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    attempts = 0
    original_replace = Path.replace

    def transient_replace(path: Path, destination: Path) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError("temporarily locked")
        return original_replace(path, destination)

    monkeypatch.setattr(Path, "replace", transient_replace)
    monkeypatch.setattr(artifacts.os, "name", "nt")
    monkeypatch.setattr(artifacts.time, "sleep", lambda _seconds: None)

    assert replace_directory(source, target) == target
    assert attempts == 2
    assert target.is_dir()
