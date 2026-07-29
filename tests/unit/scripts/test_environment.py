"""Environment検査・準備commandの契約。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts._infra.artifacts import ArtifactLayout
from scripts._infra.process import CommandResult
from scripts.environment import manager


def test_environment_manager_import_does_not_load_deep_supabase_dependencies() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import scripts.environment.manager; "
                "assert 'scripts.supabase.preflight' not in sys.modules"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


class _Distribution:
    def __init__(self, name: str, version: str, record: str | None) -> None:
        self.metadata = {"Name": name}
        self.version = version
        self._record = record

    def read_text(self, filename: str) -> str | None:
        assert filename == "RECORD"
        return self._record


def test_python_installation_fingerprint_covers_name_version_and_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    distributions = [
        _Distribution("Example_Package", "1.0", "example.py,sha256=first,1\n"),
        _Distribution("Other", "2.0", None),
    ]
    monkeypatch.setattr(manager.importlib.metadata, "distributions", lambda: distributions)
    baseline = manager.python_installation_fingerprint()
    distributions.reverse()
    assert manager.python_installation_fingerprint() == baseline
    distributions[0].version = "2.1"
    assert manager.python_installation_fingerprint() != baseline


def test_path_fingerprint_ignores_generated_python_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "src"
    cache = source / "__pycache__"
    cache.mkdir(parents=True)
    module = source / "module.py"
    bytecode = cache / "module.pyc"
    module.write_text("value = 1\n", encoding="utf-8")
    bytecode.write_bytes(b"first")
    monkeypatch.setattr(manager, "REPOSITORY_ROOT", tmp_path)

    baseline = manager._paths_fingerprint(("src",))
    bytecode.write_bytes(b"second")

    assert manager._paths_fingerprint(("src",)) == baseline
    module.write_text("value = 2\n", encoding="utf-8")
    assert manager._paths_fingerprint(("src",)) != baseline


@pytest.mark.parametrize("legacy", ["auto", "focus", "check", "release", "deep"])
def test_environment_rejects_legacy_quality_profiles(legacy: str) -> None:
    with pytest.raises(ValueError, match="未定義の環境target"):
        manager.inspect_environment(legacy, run_id="run")


def test_environment_rejects_unsupported_python_before_profile_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(manager.shutil, "which", lambda command: command)
    monkeypatch.setattr(manager.sys, "version_info", (3, 15, 0))

    report = manager.inspect_environment("quality", run_id="run")

    assert report.state == "blocked"
    assert report.error_code == manager.ERROR_PYTHON_UNSUPPORTED


def test_quality_check_reports_stopped_docker_before_later_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(manager.shutil, "which", lambda command: command)

    def execute(command: tuple[str, ...], **_kwargs: object) -> CommandResult:
        commands.append(command)
        return CommandResult(list(command), 1, 0.0, "daemon unavailable")

    monkeypatch.setattr(manager, "_execute", execute)
    report = manager.inspect_environment("quality", run_id="run")

    assert report.state == "blocked"
    assert report.error_code == manager.ERROR_DOCKER_DAEMON_UNAVAILABLE
    assert report.next_actions[0] == "Docker Desktopを起動してください。"
    assert commands == [("docker", "info")]


def test_environment_summary_exposes_failure_code_and_safe_detail() -> None:
    report = manager.EnvironmentReport(
        1,
        "run",
        "check",
        "quality",
        "quality",
        "blocked",
        "start",
        "finish",
        [
            manager.EnvironmentCheck(
                manager.ERROR_DOCKER_DAEMON_UNAVAILABLE,
                "blocked",
                "Docker daemonへ接続できません。",
                {"detail": "daemon stderr"},
            )
        ],
        [],
        ["Docker daemonへ接続できません。"],
        ["後続は未確認です。"],
        ["Docker Desktopを起動してください。"],
        [],
        manager.ERROR_DOCKER_DAEMON_UNAVAILABLE,
    )

    summary = manager._summary(report)

    assert manager.ERROR_DOCKER_DAEMON_UNAVAILABLE in summary
    assert "daemon stderr" in summary
    assert "Docker Desktopを起動してください。" in summary


def test_setup_does_not_mutate_when_prerequisite_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked = manager.EnvironmentCheck(
        manager.ERROR_DOCKER_DAEMON_UNAVAILABLE,
        "blocked",
        "Docker daemonへ接続できません。",
    )
    monkeypatch.setattr(manager, "_prerequisite_checks", lambda *_args: [blocked])
    monkeypatch.setattr(manager, "_publish_report", lambda *_args, **_kwargs: Path("report"))
    monkeypatch.setattr(
        manager,
        "_setup_locked",
        lambda *_args: pytest.fail("変更処理を開始してはいけません。"),
    )

    report = manager.setup("quality")

    assert report.state == "blocked"
    assert report.error_code == manager.ERROR_DOCKER_DAEMON_UNAVAILABLE


def test_check_distinguishes_internal_inspection_error_from_missing_prerequisite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """状態検査自体の失敗を利用者環境の不足として扱わない。"""
    monkeypatch.setattr(
        manager,
        "_prerequisite_checks",
        lambda *_args: [manager.EnvironmentCheck("environment.uv", "passed", "uv ready")],
    )
    monkeypatch.setattr(
        manager,
        "_state_check",
        lambda _profile: (_ for _ in ()).throw(OSError("state unreadable")),
    )

    report = manager.inspect_environment("python", run_id="run")

    assert report.state == "error"
    assert report.error_code == manager.ERROR_COMMAND_FAILED
    assert report.checks[-1].state == "error"


def test_setup_does_not_mutate_when_prerequisite_inspection_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = manager.EnvironmentCheck(
        manager.ERROR_CLEANUP_FAILED,
        "error",
        "一時profileを削除できませんでした。",
    )
    monkeypatch.setattr(manager, "_prerequisite_checks", lambda *_args: [failure])
    monkeypatch.setattr(manager, "_publish_report", lambda *_args, **_kwargs: Path("report"))
    monkeypatch.setattr(
        manager,
        "_setup_locked",
        lambda *_args: pytest.fail("変更処理を開始してはいけません。"),
    )

    report = manager.setup("quality")

    assert report.state == "error"
    assert report.error_code == manager.ERROR_CLEANUP_FAILED


@pytest.mark.parametrize(
    ("missing", "buildx_returncode", "supabase_version", "expected"),
    [
        ("docker", 0, manager.SUPABASE_CLI_VERSION, manager.ERROR_DOCKER_CLI_UNAVAILABLE),
        (None, 1, manager.SUPABASE_CLI_VERSION, manager.ERROR_BUILDX_UNAVAILABLE),
        ("supabase", 0, manager.SUPABASE_CLI_VERSION, manager.ERROR_SUPABASE_CLI_UNAVAILABLE),
        (None, 0, "2.105.0", manager.ERROR_SUPABASE_VERSION_MISMATCH),
    ],
)
def test_quality_prerequisites_have_distinct_error_codes(
    monkeypatch: pytest.MonkeyPatch,
    missing: str | None,
    buildx_returncode: int,
    supabase_version: str,
    expected: str,
) -> None:
    monkeypatch.setattr(
        manager.shutil,
        "which",
        lambda command: None if command == missing else command,
    )

    def execute(command: tuple[str, ...], **_kwargs: object) -> CommandResult:
        if command[:3] == ("docker", "buildx", "version"):
            return CommandResult(list(command), buildx_returncode, 0.0, "")
        if command[:2] == ("supabase", "--version"):
            return CommandResult(list(command), 0, 0.0, supabase_version)
        return CommandResult(list(command), 0, 0.0, "")

    monkeypatch.setattr(manager, "_execute", execute)

    report = manager.inspect_environment("quality", run_id="run")

    assert report.error_code == expected


def test_setup_python_only_synchronizes_python_and_writes_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(manager.shutil, "which", lambda command: command)
    monkeypatch.setattr(
        manager,
        "_execute",
        lambda command, **_kwargs: (
            commands.append(tuple(command)) or CommandResult(list(command), 0, 0.0, "")
        ),
    )
    written: list[tuple[str, list[dict[str, str]]]] = []
    monkeypatch.setattr(
        manager,
        "_write_state",
        lambda profile, images: written.append((profile, images)),
    )

    failure, cleanup = manager._setup_locked("python", "run")

    assert failure is None
    assert cleanup is None
    assert commands == [("uv", "sync", "--frozen", "--all-groups", "--all-extras")]
    assert written == [("python", [])]


def test_development_setup_prepares_supabase_without_buildx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(manager.shutil, "which", lambda command: command)
    monkeypatch.setattr(
        manager,
        "_execute",
        lambda command, **_kwargs: (
            commands.append(tuple(command)) or CommandResult(list(command), 0, 0.0, "")
        ),
    )
    monkeypatch.setattr(
        manager,
        "_prepare_supabase_images",
        lambda _run_id: (None, None, [{"reference": "supabase", "image_id": "sha256:id"}]),
    )
    written: list[tuple[str, list[dict[str, str]]]] = []
    monkeypatch.setattr(
        manager, "_write_state", lambda target, images: written.append((target, images))
    )

    failure, cleanup = manager._setup_locked("development", "run")

    assert failure is None
    assert cleanup is None
    assert not any(command[:2] == ("docker", "buildx") for command in commands)
    assert written == [("development", [{"reference": "supabase", "image_id": "sha256:id"}])]


def test_setup_failure_report_contains_stage_exit_duration_and_log_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(manager, "STATE_ROOT", tmp_path / "state")
    monkeypatch.setattr(manager, "LOCK_PATH", tmp_path / "state" / "setup.lock")
    monkeypatch.setattr(
        manager,
        "_prerequisite_checks",
        lambda *_args: [manager.EnvironmentCheck("environment.uv", "passed", "uv ready")],
    )
    failure = manager._ExecutionFailure(
        "python-sync",
        CommandResult(["uv", "sync"], 3, 1.25, "failed output"),
    )
    monkeypatch.setattr(manager, "_setup_locked", lambda *_args: (failure, None))
    monkeypatch.setattr(manager, "_publish_report", lambda *_args, **_kwargs: Path("report"))

    report = manager.setup("python")

    assert report.state == "error"
    evidence = report.checks[-1].evidence
    assert evidence == {
        "stage": "python-sync",
        "exit_code": 3,
        "duration_seconds": 1.25,
        "log": "logs/python-sync.log",
    }


def test_supabase_image_preparation_stops_only_isolated_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / "isolated"
    workdir.mkdir()
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        manager,
        "prepare_isolated_project",
        lambda _path: (workdir, "quality-project"),
    )

    def execute(command: tuple[str, ...], **_kwargs: object) -> CommandResult:
        commands.append(tuple(command))
        return CommandResult(list(command), 0, 0.0, "")

    monkeypatch.setattr(manager, "_execute", execute)
    monkeypatch.setattr(
        manager,
        "_supabase_project_images",
        lambda *_args: [{"reference": "image", "image_id": "sha256:id"}],
    )
    monkeypatch.setattr(manager, "remove_managed_path", lambda _path: None)

    failure, cleanup, images = manager._prepare_supabase_images("run")

    assert failure is None
    assert cleanup is None
    assert images == [{"reference": "image", "image_id": "sha256:id"}]
    stop = next(command for command in commands if command[:2] == ("supabase", "stop"))
    assert stop == (
        "supabase",
        "stop",
        "--project-id",
        "quality-project",
        "--no-backup",
        "--workdir",
        str(workdir),
    )


def test_image_fingerprint_is_bound_to_the_image_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(manager, "_image_label", lambda _image, _label: "expected")

    assert manager._image_fingerprint_matches("image", "application", "expected")
    assert not manager._image_fingerprint_matches("image", "application", "replaced")


def test_image_builds_embed_their_input_fingerprint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manager, "_application_image_fingerprint", lambda: "application-hash")
    monkeypatch.setattr(manager, "_e2e_image_fingerprint", lambda: "browser-hash")

    builds = manager._image_builds("docker")

    assert f"{manager._image_fingerprint_label('application')}=application-hash" in builds[0][3]
    assert (
        f"{manager._image_fingerprint_label('browser-dependencies')}=browser-hash" in builds[1][3]
    )


def test_quality_check_rejects_changed_docker_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = tmp_path / "environment"
    state_root.mkdir()
    monkeypatch.setattr(manager, "STATE_ROOT", state_root)
    monkeypatch.setattr(manager, "dependency_fingerprint", lambda _profile: "fingerprint")
    monkeypatch.setattr(manager, "_docker_context", lambda: "current")
    (state_root / "quality.json").write_text(
        json.dumps(
            {
                "fingerprint": "fingerprint",
                "target": "quality",
                "docker_context": "recorded",
                "supabase_cli_version": manager.SUPABASE_CLI_VERSION,
                "supabase_images": [],
            }
        ),
        encoding="utf-8",
    )

    result = manager._state_check("quality")

    assert result.state == "blocked"
    assert result.id == manager.ERROR_FINGERPRINT_MISMATCH
    assert result.evidence == {"recorded": "recorded", "current": "current"}


def test_supabase_start_failure_preserves_cleanup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir = tmp_path / "isolated"
    profile = tmp_path / "runtime" / "supabase-home" / "run"
    workdir.mkdir()
    profile.mkdir(parents=True)
    monkeypatch.setattr(manager, "LAYOUT", ArtifactLayout(tmp_path))
    monkeypatch.setattr(
        manager,
        "prepare_isolated_project",
        lambda _path: (workdir, "quality-project"),
    )

    def execute(command: tuple[str, ...], **_kwargs: object) -> CommandResult:
        return CommandResult(
            list(command),
            1,
            0.25,
            "start failed" if command[:2] == ("supabase", "start") else "stop failed",
        )

    monkeypatch.setattr(manager, "_execute", execute)
    monkeypatch.setattr(manager, "_remove_operation_path", lambda _path: None)

    failure, cleanup, _images = manager._prepare_supabase_images("run")

    assert failure is not None
    assert failure.stage == "supabase-start"
    assert cleanup is not None
    assert cleanup.error_code == manager.ERROR_CLEANUP_FAILED
    assert "stop failed" in cleanup.result.output


def test_report_write_failure_does_not_leave_a_nonexistent_related_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = manager.EnvironmentReport(
        1,
        "run",
        "python",
        "python",
        "check",
        "blocked",
        "start",
        "finish",
        [],
        [],
        ["cause"],
        [],
        [],
        ["operations/environment/run/report.json"],
    )
    monkeypatch.setattr(
        manager,
        "publish_operation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    assert manager._publish_report(report) is None
    assert report.related_artifacts == []
