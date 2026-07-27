"""Environment準備commandの契約。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.environment import manager
from scripts.quality import impact
from scripts.supabase.constants import LOCAL_EXCLUDED_SERVICES_CSV


class _Distribution:
    def __init__(self, name: str, version: str, record: str | None) -> None:
        self.metadata = {"Name": name}
        self.version = version
        self._record = record

    def read_text(self, filename: str) -> str | None:
        assert filename == "RECORD"
        return self._record


def test_version_returns_unavailable_when_executable_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OS policyで起動できないtoolを未準備として扱う."""
    monkeypatch.setattr(manager.shutil, "which", lambda _name: "blocked.exe")
    monkeypatch.setattr(
        manager.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("blocked")),
    )

    assert manager._version(("uv", "--version")) == "unavailable"


def test_python_installation_fingerprint_covers_name_version_and_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Installed distributionの同一性を順序に依存せず検査する。"""
    distributions = [
        _Distribution("Example_Package", "1.0", "example.py,sha256=first,1\n"),
        _Distribution("Other", "2.0", None),
    ]
    monkeypatch.setattr(manager.importlib.metadata, "distributions", lambda: distributions)
    baseline = manager.python_installation_fingerprint()

    distributions.reverse()
    assert manager.python_installation_fingerprint() == baseline

    distributions[0]._record = "other.py,sha256=changed,2\n"
    assert manager.python_installation_fingerprint() != baseline

    distributions[0]._record = None
    distributions[0].version = "2.1"
    assert manager.python_installation_fingerprint() != baseline


def test_ensure_skips_prepared_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fingerprintが一致する環境を再同期しない。"""
    monkeypatch.setattr(manager, "dependency_fingerprint", lambda _profile: "same")
    monkeypatch.setattr(manager, "_ready", lambda _profile, _fingerprint: True)
    monkeypatch.setattr(
        manager,
        "setup",
        lambda _profile: pytest.fail("setup must not run"),
    )

    assert manager.ensure("check") is False


def test_auto_environment_uses_the_change_impact_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """auto品質と環境準備が同じ実profileを選ぶ。"""
    monkeypatch.setattr(
        impact,
        "decide",
        lambda: impact.ImpactDecision("release", reason="UI change"),
    )
    observed: list[str] = []
    monkeypatch.setattr(
        manager, "dependency_fingerprint", lambda profile: observed.append(profile) or "x"
    )
    monkeypatch.setattr(manager, "_ready", lambda _profile, _fingerprint: True)

    assert manager.ensure("auto") is False
    assert observed == ["release"]


def test_setup_allows_dependency_downloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """依存準備ではregistryとimage取得を禁止しない。"""
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        manager,
        "_run",
        lambda command, **_kwargs: commands.append(tuple(command)),
    )
    monkeypatch.setattr(manager, "dependency_fingerprint", lambda _profile: "fingerprint")
    monkeypatch.setattr(manager, "STATE_ROOT", Path(".werewolf-agent/runtime/environment"))
    monkeypatch.setattr(
        manager,
        "IMAGE_STATE_ROOT",
        tmp_path / "images",
    )
    monkeypatch.setattr(Path, "mkdir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(Path, "write_text", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(manager.shutil, "which", lambda command: command)
    monkeypatch.setattr(manager, "_command_succeeds", lambda _command: True)
    monkeypatch.setattr(manager, "_image_id", lambda image: f"sha256:{image}")

    manager._setup_locked("release")

    flattened = [" ".join(command) for command in commands]
    assert any(command.startswith("uv sync --frozen") for command in flattened)
    build_commands = [command for command in flattened if command.startswith("docker buildx build")]
    assert len(build_commands) == 2
    assert any(manager.RUNTIME_IMAGE in command for command in build_commands)
    assert any(manager.E2E_IMAGE in command for command in build_commands)
    assert any(
        command.startswith("docker buildx prune") and "--max-used-space 8GB" in command
        for command in flattened
    )
    assert all("--offline" not in command for command in flattened)
    assert all("--pull=false" not in command for command in flattened)
    assert any(LOCAL_EXCLUDED_SERVICES_CSV in command for command in flattened)
    stop_indexes = [index for index, command in enumerate(flattened) if "supabase stop" in command]
    start_index = next(
        index for index, command in enumerate(flattened) if "supabase start" in command
    )
    assert len(stop_indexes) == 2
    assert stop_indexes[0] < start_index < stop_indexes[1]


def test_environment_state_is_repository_local() -> None:
    """準備状態を共有artifact root配下へ保存する。"""
    assert manager.STATE_ROOT == manager.ARTIFACT_ROOT / "runtime" / "environment"


def test_quiet_environment_command_does_not_inherit_terminal_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """秘密値を含み得る準備commandの出力をterminalへ流さない。"""
    observed: dict[str, object] = {}

    def fake_run(_command: list[str], **kwargs: object) -> SimpleNamespace:
        observed.update(kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(manager.subprocess, "run", fake_run)

    manager._run(("supabase", "start"), quiet=True)

    assert observed["capture_output"] is True
    assert observed["text"] is True


def test_release_marker_is_not_ready_when_required_images_are_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """保存済みmarkerだけではrelease準備済みと判定しない。"""
    repository = tmp_path / "repository"
    state_root = repository / ".werewolf-agent" / "runtime" / "environment"
    (repository / ".venv").mkdir(parents=True)
    state_root.mkdir(parents=True)
    (state_root / "release.json").write_text(
        json.dumps({"fingerprint": "same", "profile": "release"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(manager, "REPOSITORY_ROOT", repository)
    monkeypatch.setattr(manager, "STATE_ROOT", state_root)
    monkeypatch.setattr(manager, "_release_environment_ready", lambda _profile: False)

    assert manager._ready("release", "same") is False


def test_release_readiness_rejects_stopped_docker_daemon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Docker CLIがあってもdaemonへ接続できなければ準備済みにしない。"""
    monkeypatch.setattr(manager.shutil, "which", lambda _command: "docker")
    monkeypatch.setattr(manager, "_command_succeeds", lambda _command: False)
    monkeypatch.setattr(manager, "_image_marker_matches", lambda *_args: False)

    assert manager._release_environment_ready("release") is False


def test_release_readiness_requires_every_declared_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """現在のDocker contextに全必須imageがある場合だけ準備済みにする。"""
    observed: list[tuple[str, ...]] = []
    monkeypatch.setattr(manager.shutil, "which", lambda _command: "docker")

    def succeeds(command: tuple[str, ...]) -> bool:
        observed.append(command)
        return True

    monkeypatch.setattr(manager, "_command_succeeds", succeeds)
    monkeypatch.setattr(manager, "_image_marker_matches", lambda *_args: True)

    assert manager._release_environment_ready("release") is True
    assert observed[0] == ("docker", "info")
    assert [command[-1] for command in observed[1:]] == list(manager.REQUIRED_LOCAL_IMAGES)
    assert manager._release_environment_ready("check") is True


def test_image_marker_rejects_a_replaced_tag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同名tagが別imageを指す場合はfingerprint一致でも再利用しない。"""
    marker_root = tmp_path / "images"
    marker_root.mkdir()
    (marker_root / "application.json").write_text(
        json.dumps(
            {
                "fingerprint": "same",
                "image": manager.RUNTIME_IMAGE,
                "image_id": "sha256:expected",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(manager, "IMAGE_STATE_ROOT", marker_root)
    monkeypatch.setattr(manager, "_image_id", lambda _image: "sha256:replaced")

    assert not manager._image_marker_matches(manager.RUNTIME_IMAGE, "application", "same")
