"""品質runnerの公開仕様を検査する。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from scripts import _support as support
from scripts import quality
from scripts._support import (
    ARTIFACT_ROOT,
    quality_environment,
    redact,
    redact_artifacts,
    run_command,
)

ROOT = Path(__file__).resolve().parents[3]


def _write_contract_sdist(path: Path) -> None:
    """pyproject.tomlの公開source契約を満たす最小sdistを作る。"""
    with tarfile.open(path, mode="w:gz") as archive:
        for source in quality._sdist_contract():
            repository_path = ROOT / source
            member = (
                f"package/{source}"
                if repository_path.is_file()
                else f"package/{source}/contract-placeholder"
            )
            info = tarfile.TarInfo(member)
            content = b"contract"
            info.size = len(content)
            archive.addfile(info, BytesIO(content))


def test_quality_settings_are_loaded_from_pyproject() -> None:
    """runnerの可変値をpyproject.tomlへ一元化する。"""

    settings = quality.load_quality_settings()

    assert settings.max_jobs == 4
    assert settings.retention_days == 14
    assert settings.benchmark_min_rounds == 5
    assert settings.benchmark_max_mean_ms == 10
    assert settings.coverage_fail_under == 74
    assert settings.branch_coverage_fail_under == 48
    assert settings.timeouts == {
        "quick": 60,
        "check": 180,
        "release": 900,
        "deep": 1200,
    }


def test_pytest_can_import_application_and_quality_foundation() -> None:
    """pytest実行形式によらずsrcとscriptsを収集できる設定にする。"""

    document = quality._load_pyproject()
    pytest_options = document["tool"]["pytest"]["ini_options"]

    assert pytest_options["pythonpath"] == [".", "src"]


def test_invalid_quality_settings_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不正な品質設定で既定値へ黙ってfallbackしない。"""

    (tmp_path / "pyproject.toml").write_text(
        """
[tool.werewolf-quality]
benchmark_max_mean_ms = 10
benchmark_min_rounds = 5
branch_coverage_fail_under = 48
max_jobs = 0
retention_days = 14
[tool.werewolf-quality.timeouts]
quick = 60
check = 180
release = 600
deep = 1200
[tool.coverage.report]
fail_under = 74
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(quality, "REPOSITORY_ROOT", tmp_path)

    with pytest.raises(ValueError, match="max_jobs"):
        quality.load_quality_settings()


def test_invalid_coverage_threshold_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """coverage下限を有効な百分率の範囲に限定する。"""

    (tmp_path / "pyproject.toml").write_text(
        """
[tool.werewolf-quality]
benchmark_max_mean_ms = 10
benchmark_min_rounds = 5
branch_coverage_fail_under = 48
max_jobs = 4
retention_days = 14
[tool.werewolf-quality.timeouts]
quick = 60
check = 180
release = 600
deep = 1200
[tool.coverage.report]
fail_under = 101
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(quality, "REPOSITORY_ROOT", tmp_path)

    with pytest.raises(ValueError, match="fail_under"):
        quality.load_quality_settings()


def test_profiles_have_expected_order_and_isolated_commands() -> None:
    """profileは上位になるほど前levelを包含する。"""

    quick = {gate.name for stage in quality._profile_stages("quick", 1) for gate in stage}
    check = {gate.name for stage in quality._profile_stages("check", 1) for gate in stage}
    release = {gate.name for stage in quality._profile_stages("release", 1) for gate in stage}
    deep = {gate.name for stage in quality._profile_stages("deep", 1) for gate in stage}

    assert quick < check < release < deep
    assert {"pytest", "mypy", "eslint", "vitest"} <= quick
    assert {"coverage", "docs", "package", "benchmark"} <= check
    assert {"supabase-preflight", "integration", "docker"} <= release
    assert "deep-tests" in deep
    assert all(gate.command for stage in quality._profile_stages("deep", 1) for gate in stage)


def test_scripts_do_not_import_tests() -> None:
    """scriptsはpytest CLIだけを境界としてtestsを扱う。"""

    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((ROOT / "scripts").glob("*.py"))
    )

    assert "from tests" not in sources
    assert "import tests" not in sources


def test_quality_environment_removes_secrets_and_disables_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """子processへ有料providerの秘密情報を渡さない。"""

    monkeypatch.setenv("OPENAI_API_KEY", "paid-secret")
    monkeypatch.setenv("WEREWOLF_TOKEN", "private-token")
    monkeypatch.setenv("HTTPS_PROXY", "https://external-proxy.example")

    environment = quality_environment()

    assert "OPENAI_API_KEY" not in environment
    assert "WEREWOLF_TOKEN" not in environment
    assert environment["WEREWOLF_LLM_PROVIDER"] == "fake"
    assert environment["OTEL_SDK_DISABLED"] == "true"
    assert environment["HTTPS_PROXY"] == "http://127.0.0.1:9"
    assert environment["https_proxy"] == "http://127.0.0.1:9"
    assert environment["NO_PROXY"] == "127.0.0.1,localhost,::1"


def test_quality_environment_cannot_override_offline_invariants() -> None:
    """追加する接続情報からもsecretを除き、安全設定を最後に強制する。"""

    environment = quality_environment(
        extra={
            "OPENAI_API_KEY": "paid-secret",
            "HTTPS_PROXY": "https://external-proxy.example",
            "WEREWOLF_LLM_PROVIDER": "openai",
        }
    )

    assert "OPENAI_API_KEY" not in environment
    assert environment["HTTPS_PROXY"] == "http://127.0.0.1:9"
    assert environment["WEREWOLF_LLM_PROVIDER"] == "fake"


def test_quality_environment_keeps_only_explicit_public_supabase_keys() -> None:
    """local E2Eに必要な公開鍵だけをsecret除外規則から外す。"""
    environment = quality_environment(
        extra={
            "OPENAI_API_KEY": "paid-secret",
            "VITE_SUPABASE_PUBLISHABLE_KEY": "local-public-key",
            "WEREWOLF_SUPABASE_PUBLISHABLE_KEY": "local-public-key",
        }
    )

    assert "OPENAI_API_KEY" not in environment
    assert environment["VITE_SUPABASE_PUBLISHABLE_KEY"] == "local-public-key"
    assert environment["WEREWOLF_SUPABASE_PUBLISHABLE_KEY"] == "local-public-key"


def test_browser_e2e_uses_the_shared_offline_environment() -> None:
    """ReactとStreamlitの共通E2Eへ安全な子process環境だけを渡す。"""
    source = (ROOT / "scripts" / "e2e.py").read_text(encoding="utf-8")

    assert "quality_environment(" in source
    assert "WEREWOLF_LLM_PROVIDER" not in source
    assert '"build"' not in source
    assert '"never"' in source


def test_offline_gate_rejects_overridden_network_guard(tmp_path: Path) -> None:
    """子process環境の遮断設定が上書きされた実行を拒否する。"""

    environment = quality_environment()
    environment["HTTPS_PROXY"] = "https://external-proxy.example"
    context = SimpleNamespace(environment=environment)

    result = quality._offline_guard_action(context, tmp_path)

    assert result.returncode == 1
    assert "HTTPS_PROXY" in result.output


def test_redact_masks_secret_values() -> None:
    """AI向けlogにもsecretの値を残さない。"""

    output = redact("api_key=abc token:xyz role=werewolf target_id=p2 ordinary=value")

    assert "abc" not in output
    assert "xyz" not in output
    assert "werewolf" not in output
    assert "p2" not in output
    assert output.endswith("ordinary=value")


def test_redact_masks_credentials_embedded_in_url() -> None:
    """接続URLに埋め込まれたpasswordを成果物へ残さない。"""

    output = redact("dsn=postgresql://postgres:local-password@127.0.0.1:5432/postgres")

    assert "local-password" not in output
    assert output == ("dsn=postgresql://postgres:[REDACTED]@127.0.0.1:5432/postgres")


def test_redact_artifacts_keeps_json_valid_and_masks_failure_details(
    tmp_path: Path,
) -> None:
    """失敗時のJUnitやJSONにも設定値とprivate stateを残さない。"""

    report = tmp_path / "result.json"
    report.write_text(
        '{"openai_api_key":"paid-secret","role":"werewolf","state":"failed"}',
        encoding="utf-8",
    )
    junit = tmp_path / "result.xml"
    junit.write_text(
        "<failure>openai_api_key=SecretStr('paid-secret'), target_id='p2'</failure>",
        encoding="utf-8",
    )

    redact_artifacts(tmp_path)

    assert json.loads(report.read_text(encoding="utf-8")) == {
        "openai_api_key": "[REDACTED]",
        "role": "[REDACTED]",
        "state": "failed",
    }
    junit_text = junit.read_text(encoding="utf-8")
    assert "paid-secret" not in junit_text
    assert "p2" not in junit_text


def test_deep_requires_confirmation(capsys: pytest.CaptureFixture[str]) -> None:
    """deepはprofile名だけでは開始しない。"""

    assert quality.main(["deep"]) == 2
    assert "--confirm-deep" in capsys.readouterr().err


def test_configuration_failure_returns_infrastructure_exit_code(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """設定異常を品質違反ではなく実行基盤異常として終了する。"""

    monkeypatch.setattr(
        quality,
        "load_quality_settings",
        lambda: (_ for _ in ()).throw(ValueError("invalid config")),
    )

    assert quality.main(["quick"]) == 2
    assert "品質設定を読み込めません" in capsys.readouterr().err


def test_clean_failure_returns_infrastructure_exit_code(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cleanupのI/O異常を品質違反として扱わない。"""

    monkeypatch.setattr(
        quality,
        "clean",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("locked")),
    )

    assert quality.main(["clean"]) == 2
    assert "成果物を削除できません" in capsys.readouterr().err


def test_clean_preserves_persistent_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cleanはDB、運用log、QA、最新runを保持する。"""

    artifact_root = tmp_path / ".werewolf-agent"
    build = artifact_root / "build"
    cache = artifact_root / "cache" / "pytest"
    coverage = artifact_root / "coverage"
    for path in (
        build,
        cache,
        coverage,
        artifact_root / "db",
        artifact_root / "logs",
        artifact_root / "qa",
    ):
        path.mkdir(parents=True)
    package_cache = artifact_root / "cache" / "uv"
    package_cache.mkdir(parents=True)
    temporary_root = tmp_path / "temporary" / "werewolf-agent"
    temporary_cache = temporary_root / "pytest"
    temporary_cache.mkdir(parents=True)
    latest_run = artifact_root / "quality" / "runs" / "latest"
    latest_run.mkdir(parents=True)
    latest = artifact_root / "quality" / "latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps({"run_id": "latest"}), encoding="utf-8")

    monkeypatch.setattr(quality, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(quality, "QUALITY_ROOT", artifact_root / "quality")
    monkeypatch.setattr(quality, "BUILD_DIRECTORIES", (build, cache, coverage))
    monkeypatch.setattr(quality, "TEMPORARY_CACHE_DIRECTORIES", (temporary_cache,))
    monkeypatch.setattr("scripts._support.ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr("scripts._support.TEMPORARY_ROOT", temporary_root)

    quality.clean(retention_days=0)

    assert not build.exists()
    assert not cache.exists()
    assert not coverage.exists()
    assert (artifact_root / "db").exists()
    assert (artifact_root / "logs").exists()
    assert (artifact_root / "qa").exists()
    assert package_cache.exists()
    assert not temporary_cache.exists()
    assert latest_run.exists()
    assert latest.exists()


def test_clean_preserves_newest_run_when_latest_reference_is_corrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """latest.jsonが壊れていても実際の最新runを削除しない。"""

    artifact_root = tmp_path / ".werewolf-agent"
    runs = artifact_root / "quality" / "runs"
    older = runs / "older"
    newest = runs / "newest"
    older.mkdir(parents=True)
    newest.mkdir()
    os.utime(older, (1, 1))
    os.utime(newest, (2, 2))
    latest = artifact_root / "quality" / "latest.json"
    latest.write_text("{broken", encoding="utf-8")

    monkeypatch.setattr(quality, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(quality, "QUALITY_ROOT", artifact_root / "quality")
    monkeypatch.setattr(quality, "BUILD_DIRECTORIES", ())
    monkeypatch.setattr(quality, "TEMPORARY_CACHE_DIRECTORIES", ())
    monkeypatch.setattr(support, "ARTIFACT_ROOT", artifact_root)

    quality.clean(retention_days=0)

    assert not older.exists()
    assert newest.exists()
    assert latest.exists()


@pytest.mark.parametrize(
    "arguments",
    [
        ["quick", "--jobs", "0"],
        ["quick", "--jobs", "5"],
        ["quick", "--timeout", "0"],
        ["clean", "--retention-days", "-1"],
    ],
)
def test_cli_rejects_unsafe_numeric_options(arguments: list[str]) -> None:
    """worker、timeout、保持期間の危険な境界値を開始前に拒否する。"""

    with pytest.raises(SystemExit) as captured:
        quality.main(arguments)

    assert captured.value.code == 2


def test_remove_managed_path_retries_transient_directory_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OneDrive等の一時的な削除競合を短時間だけ再試行する。"""

    artifact_root = tmp_path / ".werewolf-agent"
    target = artifact_root / "build"
    target.mkdir(parents=True)
    attempts = 0
    real_rmtree = support.shutil.rmtree

    def flaky_rmtree(path: Path, **kwargs: object) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError(145, "directory is not empty")
        real_rmtree(path, **kwargs)

    monkeypatch.setattr(support, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(support.shutil, "rmtree", flaky_rmtree)
    monkeypatch.setattr(support.time, "sleep", lambda _seconds: None)

    support.remove_managed_path(target)

    assert attempts == 2
    assert not target.exists()


def test_remove_temporary_path_rejects_path_outside_owned_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一時cache削除で品質用ルート外へ出ない。"""

    temporary_root = tmp_path / "temporary" / "werewolf-agent"
    temporary_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(support, "TEMPORARY_ROOT", temporary_root)

    with pytest.raises(ValueError, match="管理領域外"):
        support.remove_temporary_path(outside)


def test_quality_environment_prepares_temporary_cache_parents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """手動clean後もrunner初期化でtool cacheの親を再作成する。"""

    directories = (tmp_path / "pytest", tmp_path / "mypy")
    monkeypatch.setattr(support, "TEMPORARY_CACHE_DIRECTORIES", directories)
    monkeypatch.setattr(support, "TEMPORARY_ROOT", tmp_path)

    environment = support.quality_environment(run_dir=tmp_path / "run")

    assert all(path.is_dir() for path in directories)
    assert environment["SUPABASE_HOME"] == str(tmp_path / "supabase" / "run")


def test_artifact_root_is_repository_local() -> None:
    """生成物の既定位置を単一の管理領域へ固定する。"""

    assert ARTIFACT_ROOT.name == ".werewolf-agent"


def test_profile_commands_write_machine_readable_results_to_run_directory(
    tmp_path: Path,
) -> None:
    """pytest、coverage、benchmarkの成果物を同じrunへ関連付ける。"""

    commands = [
        argument
        for stage in quality._profile_stages("deep", 1, tmp_path)
        for gate in stage
        for argument in gate.command
    ]
    settings = quality.load_quality_settings()
    commands.extend(quality._benchmark_command(tmp_path, settings))

    assert str(tmp_path / "test-results" / "quick.xml") in commands
    assert f"xml:{tmp_path / 'coverage' / 'coverage.xml'}" in commands
    assert "--cov-fail-under=74" in commands
    assert "--benchmark-disable-gc" in commands
    assert "--benchmark-min-rounds=5" in commands
    assert str(tmp_path / "benchmarks" / "core.json") in commands
    assert str(tmp_path / "test-results" / "integration.xml") in commands
    assert str(tmp_path / "test-results" / "deep.xml") in commands


def test_benchmark_contract_rejects_performance_regression(tmp_path: Path) -> None:
    """平均時間が設定上限を超えたbenchmarkを品質違反にする。"""

    result = tmp_path / "benchmark.json"
    result.write_text(
        json.dumps(
            {
                "benchmarks": [
                    {
                        "name": "core",
                        "stats": {"mean": 0.011},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    errors, measurements = quality._benchmark_contract(result, maximum_mean_ms=10)

    assert measurements == [("core", 11.0)]
    assert errors == ["coreの平均11.000msが上限10msを超えました。"]


def test_benchmark_contract_accepts_result_within_limit(tmp_path: Path) -> None:
    """設定上限内のbenchmark結果を受理する。"""

    result = tmp_path / "benchmark.json"
    result.write_text(
        json.dumps(
            {
                "benchmarks": [
                    {
                        "name": "core",
                        "stats": {"mean": 0.001},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert quality._benchmark_contract(result, maximum_mean_ms=10) == (
        [],
        [("core", 1.0)],
    )


def test_distribution_contract_reports_missing_resources_and_entrypoints(
    tmp_path: Path,
) -> None:
    """配布物の欠落をCheckで調査可能な粒度へ分解する。"""

    _write_contract_sdist(tmp_path / "package.tar.gz")
    with ZipFile(tmp_path / "package.whl", "w") as wheel:
        wheel.writestr("package.dist-info/entry_points.txt", "[console_scripts]\n")

    errors = quality._distribution_contract_errors(tmp_path)

    assert any("defaults.toml" in error for error in errors)
    assert any("werewolf-agent =" in error for error in errors)
    assert any("werewolf-agent-worker =" in error for error in errors)


def test_distribution_contract_accepts_complete_wheel(tmp_path: Path) -> None:
    """全resourceとconsole entrypointを含む配布物を受理する。"""

    _write_contract_sdist(tmp_path / "package.tar.gz")
    resources, entrypoints = quality._distribution_contract()
    with ZipFile(tmp_path / "package.whl", "w") as wheel:
        wheel.writestr(
            "package.dist-info/entry_points.txt",
            "[console_scripts]\n" + "\n".join(entrypoints) + "\n",
        )
        for resource in resources:
            wheel.writestr(resource, "content")

    assert quality._distribution_contract_errors(tmp_path) == []


def test_distribution_contract_rejects_unreadable_sdist(tmp_path: Path) -> None:
    """壊れたsource配布物を存在だけで合格させない。"""

    (tmp_path / "package.tar.gz").write_bytes(b"not-a-tar")
    resources, entrypoints = quality._distribution_contract()
    with ZipFile(tmp_path / "package.whl", "w") as wheel:
        wheel.writestr(
            "package.dist-info/entry_points.txt",
            "[console_scripts]\n" + "\n".join(entrypoints) + "\n",
        )
        for resource in resources:
            wheel.writestr(resource, "content")

    errors = quality._distribution_contract_errors(tmp_path)

    assert any("sdistを読み取れません" in error for error in errors)


def test_branch_coverage_contract_enforces_independent_threshold(tmp_path: Path) -> None:
    """総合coverageとは別に実際のbranch rateの退行を検出する。"""

    result_path = tmp_path / "coverage.xml"
    result_path.write_text(
        '<coverage line-rate="0.75" branch-rate="0.478"/>',
        encoding="utf-8",
    )

    errors, percentage = quality._branch_coverage_contract(
        result_path,
        minimum_percentage=48,
    )

    assert percentage == pytest.approx(47.8)
    assert errors == ["branch coverage 47.80% は下限 48% を下回っています。"]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (
            [
                "--collect-only",
                "tests/integration/package/test_distribution.py",
            ],
            "Selected tests require --test-level=release.",
        ),
        (
            [
                "--collect-only",
                "--test-level=deep",
                "-m",
                "deep",
                "tests/unit/domain/test_domain_game.py",
            ],
            "deepの実行には--confirm-deepが必要です。",
        ),
    ],
)
def test_pytest_rejects_accidental_heavy_selection(
    arguments: list[str],
    message: str,
) -> None:
    """実際のpytest入口でも重いtestの誤選択を非0で拒否する。"""

    environment = quality_environment()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    assert message in result.stdout + result.stderr


def test_run_command_reports_timeout_without_leaving_process_running() -> None:
    """timeoutを品質違反と区別できる終了値で返す。"""

    result = run_command(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        timeout_seconds=1,
        environment=quality_environment(),
    )

    assert result.returncode == 124
    assert result.timed_out is True
    assert result.duration_seconds < 10


def test_run_command_keeps_raw_output_internal_and_redacts_log() -> None:
    """接続値は内部処理へ渡し、同じ値をlogへは残さない。"""

    log = StringIO()
    dsn = "postgresql://postgres:local-password@127.0.0.1:5432/postgres"
    result = run_command(
        [sys.executable, "-c", f"print({dsn!r})"],
        timeout_seconds=10,
        environment=quality_environment(),
        output=log,
    )

    assert dsn in result.output
    assert "local-password" not in log.getvalue()
    assert "[REDACTED]" in log.getvalue()


def test_timeout_is_classified_as_runner_error() -> None:
    """timeoutをテスト不合格ではなく実行基盤異常として報告する。"""

    result = quality.CommandResult(
        command=["test"],
        returncode=124,
        duration_seconds=1.0,
        output="",
        timed_out=True,
    )

    assert quality._command_state(result) == "error"


@pytest.mark.parametrize(
    ("returncode", "expected"),
    [(1, "failed"), (2, "error"), (3, "error"), (4, "error"), (5, "error")],
)
def test_pytest_exit_codes_distinguish_failure_from_runner_error(
    returncode: int,
    expected: str,
) -> None:
    """pytestのtest不合格と中断・内部異常・誤用・未収集を区別する。"""

    result = quality.CommandResult(
        command=[sys.executable, "-m", "pytest", "tests"],
        returncode=returncode,
        duration_seconds=1.0,
        output="",
    )

    assert quality._command_state(result) == expected


def test_nonzero_infrastructure_command_is_classified_as_error() -> None:
    """cleanup等の非0終了を品質違反と区別する。"""

    result = quality.CommandResult(
        command=["cleanup"],
        returncode=1,
        duration_seconds=1.0,
        output="",
    )

    assert quality._command_state(result, nonzero_state="error") == "error"


def test_git_status_failure_is_not_treated_as_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Git検査失敗を空のworking treeとして扱わない。"""

    monkeypatch.setattr(
        quality,
        "run_command",
        lambda *_args, **_kwargs: quality.CommandResult(["git"], 1, 0.0, ""),
    )

    with pytest.raises(RuntimeError, match="状態を取得できません"):
        quality._git_status({})


def test_runner_setup_failure_writes_machine_readable_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gate開始前のGit検査失敗もAIが調査できる成果物へ残す。"""

    for relative in ("logs", "test-results", "coverage", "benchmarks", "browser"):
        (tmp_path / relative).mkdir()
    settings = quality.load_quality_settings()
    monkeypatch.setattr(quality, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(quality, "create_run_directory", lambda _profile: ("run", tmp_path))
    monkeypatch.setattr(quality, "quality_environment", lambda **_kwargs: {})
    monkeypatch.setattr(
        quality,
        "_git_status",
        lambda _environment: (_ for _ in ()).throw(RuntimeError("git unavailable")),
    )
    monkeypatch.setattr(quality, "write_latest", lambda *_args: None)

    state, report_path = quality.execute(
        "quick",
        jobs=1,
        timeout_seconds=1,
        settings=settings,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert state == "error"
    assert report["state"] == "error"
    assert report["results"][0]["name"] == "runner-setup"
    assert any(result["state"] == "skipped" for result in report["results"])
    assert (tmp_path / "logs" / "runner-setup.log").is_file()


def test_vscode_and_ci_use_the_shared_quality_entrypoint() -> None:
    """利用場所ごとに独自の品質判定経路を作らない。"""

    launch = json.loads((ROOT / ".vscode" / "launch.json").read_text(encoding="utf-8"))
    tasks = json.loads((ROOT / ".vscode" / "tasks.json").read_text(encoding="utf-8"))
    settings = json.loads((ROOT / ".vscode" / "settings.json").read_text(encoding="utf-8"))
    extensions = json.loads((ROOT / ".vscode" / "extensions.json").read_text(encoding="utf-8"))
    launch_names = {configuration["name"] for configuration in launch["configurations"]}
    task_commands = {
        task["label"]: task.get("args", []) for task in tasks["tasks"] if task["type"] == "process"
    }
    workflow = (ROOT / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8")

    assert {
        "Quality: Quick",
        "Quality: Check",
        "Quality: Release",
        "Quality: Deep (Confirmation Required)",
        "Tests: Current File (Quick)",
    } <= launch_names
    assert task_commands["Quality: Quick"] == ["-m", "scripts.quality", "quick"]
    assert task_commands["Quality: Check"] == ["-m", "scripts.quality", "check"]
    assert task_commands["Docs: Inspect"] == ["-m", "scripts.docs", "inspect"]
    assert task_commands["Docs: Build"] == ["-m", "scripts.docs", "build"]
    assert task_commands["Architecture: Analyze"] == ["-m", "scripts.architecture"]
    assert "python -m scripts.quality check" in workflow
    assert "python -m scripts.quality release" in workflow
    assert "python -m scripts.quality deep --confirm-deep" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "include-hidden-files: true" in workflow
    assert ".werewolf-agent/build" in workflow
    assert not (ROOT / ".github" / "workflows" / "docker.yml").exists()
    assert settings["python.testing.pytestArgs"] == ["--test-level=quick", "tests"]
    assert "flake8.enabled" not in settings
    assert "isort.serverEnabled" not in settings
    assert "ms-python.mypy-type-checker" in extensions["recommendations"]


def test_runtime_docker_dependencies_are_cached_before_source_copy() -> None:
    """Releaseは事前構築済みの現行runtime imageだけを検査する。"""

    backend = (ROOT / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")

    assert "FROM base AS runtime" in backend
    assert "USER app" in backend
    commands = quality._docker_commands("quality:test")
    assert len(commands) == 3
    assert all("--network" in command and "none" in command for command in commands)
    assert "os.geteuid() != 0" in commands[0][-1]
    assert commands[1][-2:] == ["quality:test", "--help"]
    assert "werewolf-agent-worker" in commands[1]
    assert "werewolf-agent" in commands[2]


def test_events_include_skipped_gates(tmp_path: Path) -> None:
    """途中停止後の未実行gateもAIが追跡できるeventへ残す。"""

    event_path = tmp_path / "events.jsonl"
    result = quality.GateResult(
        name="integration",
        description="Integration",
        state="skipped",
        duration_seconds=0.0,
        message="前段の品質ゲートが完了しませんでした。",
    )

    quality._append_events(event_path, [result])

    event = json.loads(event_path.read_text(encoding="utf-8"))
    assert event["gate"] == "integration"
    assert event["state"] == "skipped"
    assert event["message"]


def test_run_metrics_are_machine_readable_and_human_summarized(tmp_path: Path) -> None:
    """JUnit、coverage、benchmark、browser成果物を最上位reportへ集約する。"""

    for relative in ("test-results", "coverage", "benchmarks", "browser"):
        (tmp_path / relative).mkdir()
    (tmp_path / "test-results" / "quick.xml").write_text(
        '<testsuites><testsuite tests="7" failures="1" errors="1" skipped="1">'
        '<testsuite tests="5" failures="1" errors="0" skipped="1"/>'
        '<testsuite tests="2" failures="0" errors="1" skipped="0"/>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    (tmp_path / "coverage" / "coverage.xml").write_text(
        '<coverage lines-valid="80" lines-covered="64" branches-valid="20" '
        'branches-covered="10" line-rate="0.8" branch-rate="0.5"/>',
        encoding="utf-8",
    )
    (tmp_path / "benchmarks" / "core.json").write_text(
        json.dumps({"benchmarks": [{"name": "core", "stats": {"mean": 0.00125, "rounds": 8}}]}),
        encoding="utf-8",
    )
    (tmp_path / "browser" / "desktop.png").write_bytes(b"image")

    metrics, issues = quality._collect_run_metrics(tmp_path)
    summary = "\n".join(quality._metric_summary(metrics, issues))

    assert issues == []
    assert metrics["tests"]["quick"] == {
        "tests": 7,
        "failures": 1,
        "errors": 1,
        "skipped": 1,
        "passed": 4,
    }
    assert metrics["coverage"] == {
        "total_percent": 74.0,
        "line_percent": 80.0,
        "branch_percent": 50.0,
        "lines": {"covered": 64, "valid": 80},
        "branches": {"covered": 10, "valid": 20},
    }
    assert metrics["benchmarks"] == [{"name": "core", "mean_ms": 1.25, "rounds": 8}]
    assert metrics["browser_artifacts"] == ["browser/desktop.png"]
    assert "coverage: total 74.0%, line 80.0%, branch 50.0%" in summary
    assert "benchmark `core`: mean 1.25ms, 8 rounds" in summary


def test_run_metrics_report_malformed_artifacts_without_breaking_summary(
    tmp_path: Path,
) -> None:
    """失敗時の壊れた成果物もreport生成を妨げず調査対象として残す。"""

    for relative in ("test-results", "coverage", "benchmarks", "browser"):
        (tmp_path / relative).mkdir()
    (tmp_path / "test-results" / "quick.xml").write_text("<broken", encoding="utf-8")
    (tmp_path / "coverage" / "coverage.xml").write_text("<broken", encoding="utf-8")
    (tmp_path / "benchmarks" / "core.json").write_text("{broken", encoding="utf-8")

    metrics, issues = quality._collect_run_metrics(tmp_path)

    assert metrics["tests"] == {}
    assert len(issues) == 3
    assert {issue.split("を", maxsplit=1)[0] for issue in issues} == {
        "quick.xml",
        "coverage.xml",
        "core.json",
    }


def test_artifact_issues_change_final_state_and_exit_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """成果物解析不能をpassedにせず最上位errorへ反映する。"""

    for relative in ("test-results", "coverage", "benchmarks", "browser"):
        (tmp_path / relative).mkdir()
    (tmp_path / "test-results" / "quick.xml").write_text("<broken", encoding="utf-8")
    monkeypatch.setattr(quality, "write_latest", lambda *_args: None)
    context = quality.RunContext(
        profile="quick",
        jobs=1,
        timeout_seconds=60,
        run_id="run",
        run_dir=tmp_path,
        environment={},
        initial_git_status="",
        started_at=quality.utc_now(),
    )
    results = [
        quality.GateResult(
            name="pytest",
            description="Python quick test",
            state="passed",
            duration_seconds=1.0,
        )
    ]

    state, report_path = quality._write_summary(context, results)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert state == "error"
    assert report["state"] == "error"
    assert report["results"][-1]["name"] == "artifact-validation"
    assert report["results"][-1]["state"] == "error"
    assert events[-1]["gate"] == "artifact-validation"


def test_profiles_require_their_declared_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """0終了だけで合格させずprofileごとの成果物完全性を要求する。"""

    run_dir = tmp_path / "run"
    artifact_root = tmp_path / "artifacts"
    run_dir.mkdir()
    monkeypatch.setattr(quality, "ARTIFACT_ROOT", artifact_root)

    quick_issues = quality._required_artifact_issues("quick", run_dir)
    deep_issues = quality._required_artifact_issues("deep", run_dir)

    assert "必須成果物がありません: test-results/quick.xml" in quick_issues
    assert "必須成果物がありません: build/architecture/architecture.json" in quick_issues
    assert "必須成果物がありません: coverage/coverage.xml" in deep_issues
    assert "必須成果物がありません: build/docs/index.html" in deep_issues
    assert "必須成果物がありません: build/docs/report.json" in deep_issues
    assert "必須成果物がありません: build/frontend/index.html" in deep_issues
    assert "browser成果物がありません: desktop.png" in deep_issues
    assert "必須成果物がありません: test-results/deep.xml" in deep_issues
    assert "wheel成果物は1件必要です: 0件" in deep_issues
    assert "sdist成果物は1件必要です: 0件" in deep_issues


def test_required_artifacts_must_be_updated_by_the_current_run(tmp_path: Path) -> None:
    """前回runの成果物を今回の成功証拠として受理しない。"""

    run_dir = tmp_path / "run"
    result_path = run_dir / "test-results" / "quick.xml"
    result_path.parent.mkdir(parents=True)
    result_path.write_text("<testsuites/>", encoding="utf-8")
    os.utime(result_path, (1, 1))

    issues = quality._required_artifact_issues(
        "quick",
        run_dir,
        started_at=quality.utc_now(),
    )

    assert "必須成果物が現在runで更新されていません: test-results/quick.xml" in issues


def test_execute_stops_owned_supabase_when_runner_is_interrupted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gate間の割り込みでも品質所有Supabaseのcleanupを実行する。"""

    for relative in ("logs", "test-results", "coverage", "benchmarks", "browser"):
        (tmp_path / relative).mkdir()
    settings = quality.load_quality_settings()
    monkeypatch.setattr(quality, "REPOSITORY_ROOT", tmp_path)
    stages = [[quality.Gate("start", "start")], [quality.Gate("interrupt", "interrupt")]]
    stopped = False

    def run_gate(context: quality.RunContext, gate: quality.Gate) -> quality.GateResult:
        nonlocal stopped
        if gate.name == "start":
            context.supabase_cleanup_required = True
        elif gate.name == "interrupt":
            raise KeyboardInterrupt
        elif gate.name == "supabase-stop":
            stopped = True
        return quality.GateResult(gate.name, gate.description, "passed", 0.0)

    monkeypatch.setattr(quality, "create_run_directory", lambda _profile: ("run", tmp_path))
    monkeypatch.setattr(quality, "quality_environment", lambda **_kwargs: {})
    monkeypatch.setattr(quality, "_git_status", lambda _environment: "")
    monkeypatch.setattr(quality, "_profile_stages", lambda *_args: stages)
    monkeypatch.setattr(quality, "_run_gate", run_gate)
    monkeypatch.setattr(quality, "write_latest", lambda *_args: None)

    state, report_path = quality.execute(
        "release",
        jobs=1,
        timeout_seconds=1,
        settings=settings,
    )

    assert state == "error"
    assert stopped is True
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["state"] == "error"
    assert any(result["name"] == "runner" for result in report["results"])
    assert any(result["state"] == "skipped" for result in report["results"])


def test_supabase_cleanup_removes_isolated_cli_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """projectが既に停止済みでもrun固有SUPABASE_HOMEを削除する。"""

    temporary_root = tmp_path / "temporary" / "werewolf-agent"
    profile = temporary_root / "supabase" / "run"
    profile.mkdir(parents=True)
    context = quality.RunContext(
        profile="release",
        jobs=1,
        timeout_seconds=1,
        run_id="run",
        run_dir=tmp_path,
        environment={"SUPABASE_HOME": str(profile)},
        initial_git_status="",
        started_at=quality.utc_now(),
        supabase_workdir=tmp_path / "missing-project",
        supabase_project_id="quality-project",
    )
    monkeypatch.setattr(support, "TEMPORARY_ROOT", temporary_root)

    result = quality._supabase_stop_action(context, tmp_path / "log")

    assert result.returncode == 0
    assert not profile.exists()


def test_supabase_ownership_is_recorded_before_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """preflight割り込み前にcleanupに必要な所有情報を確定する。"""

    context = quality.RunContext(
        profile="release",
        jobs=1,
        timeout_seconds=1,
        run_id="run",
        run_dir=tmp_path,
        environment={},
        initial_git_status="",
        started_at=quality.utc_now(),
    )
    monkeypatch.setattr(quality, "ARTIFACT_ROOT", tmp_path / ".werewolf-agent")
    monkeypatch.setattr(
        quality,
        "prepare_supabase",
        lambda **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt),
    )

    with pytest.raises(KeyboardInterrupt):
        quality._supabase_action(context, tmp_path / "log")

    assert context.supabase_cleanup_required is True
    assert context.supabase_workdir is not None
    assert context.supabase_project_id == quality.isolated_project_id(context.supabase_workdir)
