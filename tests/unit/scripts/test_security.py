"""Security検査commandの契約。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.security import __main__ as security_cli
from scripts.security import dependencies, secrets


def test_dependency_audit_uses_frozen_complete_export(
    monkeypatch,
) -> None:
    """Lock済みの全extraとgroupだけを監査対象にする。"""
    commands: list[tuple[str, ...]] = []

    def completed(command: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(dependencies.subprocess, "run", completed)

    assert dependencies.audit_dependencies() == 0
    assert commands[0][:6] == (
        "uv",
        "export",
        "--all-extras",
        "--all-groups",
        "--frozen",
        "--no-emit-project",
    )
    assert "pip_audit" in commands[1]
    assert "--disable-pip" in commands[1]
    assert "--require-hashes" in commands[1]
    requirement = Path(commands[1][commands[1].index("--requirement") + 1])
    assert requirement.name == "requirements.txt"


def test_dependency_audit_stops_when_export_fails(monkeypatch) -> None:
    """不完全な依存一覧を成功として監査しない。"""
    commands: list[tuple[str, ...]] = []

    def failed(command: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 19)

    monkeypatch.setattr(dependencies.subprocess, "run", failed)

    assert dependencies.audit_dependencies() == 19
    assert len(commands) == 1


def test_security_command_rejects_unknown_operation(capsys) -> None:
    """未定義の検査を空の成功として扱わない。"""
    assert security_cli.main(["unknown"]) == 2
    assert "scripts.security {dependencies|secrets}" in capsys.readouterr().err


def test_secret_audit_scans_tracked_and_untracked_files(monkeypatch) -> None:
    """Git管理中と追加前のfileを同じbaselineで検査する。"""
    commands: list[tuple[str, ...]] = []
    scanned: list[tuple[tuple[str, ...], Path]] = []

    def completed(
        command: tuple[str, ...], **_kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        output = b"src/app.py\0.env.local\0.secrets.baseline\0" if command[0] == "git" else b""
        return subprocess.CompletedProcess(command, 0, stdout=output)

    def scan(paths: tuple[str, ...], baseline_path: Path) -> int:
        scanned.append((paths, baseline_path))
        return 0

    monkeypatch.setattr(secrets.subprocess, "run", completed)
    monkeypatch.setattr(secrets, "_scan_paths", scan)
    monkeypatch.setattr(secrets, "_utf8_mode_enabled", lambda: True)

    assert secrets.audit_secrets() == 0
    assert commands[0][:5] == (
        "git",
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
    )
    assert len(commands) == 1
    assert scanned == [(("src/app.py", ".env.local"), secrets.BASELINE_PATH)]


def test_secret_audit_stops_when_file_listing_fails(monkeypatch) -> None:
    """Git境界を確定できない場合は成功にしない。"""
    calls = 0

    def failed(command: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(command, 11, stdout=b"")

    monkeypatch.setattr(secrets.subprocess, "run", failed)
    monkeypatch.setattr(secrets, "_utf8_mode_enabled", lambda: True)

    assert secrets.audit_secrets() == 11
    assert calls == 1


def test_secret_audit_propagates_scanner_failure(monkeypatch) -> None:
    """Secret候補の検出を品質gateへ伝播する。"""

    def completed(
        command: tuple[str, ...], **_kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 0, stdout=b"config.toml\0")

    monkeypatch.setattr(secrets.subprocess, "run", completed)
    monkeypatch.setattr(secrets, "_scan_paths", lambda *_args: 1)
    monkeypatch.setattr(secrets, "_utf8_mode_enabled", lambda: True)

    assert secrets.audit_secrets() == 1


def test_secret_audit_reexecutes_in_utf8_mode(monkeypatch) -> None:
    """Windows localeでUTF-8 sourceを黙ってskipしない。"""
    commands: list[tuple[str, ...]] = []

    def completed(
        command: tuple[str, ...], **_kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(secrets.subprocess, "run", completed)
    monkeypatch.setattr(secrets, "_utf8_mode_enabled", lambda: False)

    assert secrets.audit_secrets() == 0
    assert commands == [
        (
            secrets.sys.executable,
            "-X",
            "utf8",
            "-m",
            "scripts.security",
            "secrets",
        )
    ]


def test_secret_scan_does_not_mutate_the_baseline() -> None:
    """複数fileの分割検査でbaselineの例外を削除しない。"""
    original = secrets.BASELINE_PATH.read_bytes()

    assert (
        secrets._scan_paths(
            (
                "tests/fixtures/redaction_cases.json",
                "tests/unit/observability/test_logging.py",
            ),
            secrets.BASELINE_PATH,
        )
        == 0
    )
    assert secrets.BASELINE_PATH.read_bytes() == original


def test_secret_scan_rejects_a_new_candidate(tmp_path: Path) -> None:
    """Baselineにないcredential候補を成功扱いしない。"""
    candidate = tmp_path / "runtime.py"
    key_name = "pass" + "word"
    value = "not-for-" + "production-123"
    candidate.write_text(f'{key_name} = "{value}"\n', encoding="utf-8")

    assert secrets._scan_paths((str(candidate),), secrets.BASELINE_PATH) == 1


def test_secret_baseline_contains_only_audited_test_fixtures() -> None:
    """Productや運用設定のsecret候補をbaselineで握りつぶさない。"""
    root = Path(__file__).resolve().parents[3]
    baseline = json.loads((root / ".secrets.baseline").read_text(encoding="utf-8"))

    assert baseline["results"]
    assert all(path.startswith("tests/") for path in baseline["results"])
