"""品質runnerの公開仕様を検査する。"""

from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import time
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts._infra import process as support
from scripts._infra.process import (
    ARTIFACT_ROOT,
    quality_environment,
    redact,
    redact_artifacts,
    run_command,
)
from scripts.quality import repository as repository_state
from scripts.quality import retention
from scripts.quality import runner as quality
from scripts.quality.gates import distribution, runtime
from scripts.quality.gates import environment as environment_gate
from scripts.quality.gates import tests as test_gates
from scripts.quality.repository import RepositorySnapshot

ROOT = Path(__file__).resolve().parents[3]
REDACTION_CASES = json.loads(
    (ROOT / "tests" / "fixtures" / "redaction_cases.json").read_text(encoding="utf-8")
)


def _write_contract_sdist(path: Path) -> None:
    """pyproject.tomlの公開source契約を満たす最小sdistを作る。"""
    with tarfile.open(path, mode="w:gz") as archive:
        for source in distribution.sdist_contract():
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

    assert settings.default_jobs == 2
    assert settings.max_jobs == 4
    assert settings.benchmark_min_rounds == 5
    assert settings.timeouts == {
        "focus": 180,
        "check": 300,
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
benchmark_min_rounds = 5
default_jobs = 1
max_jobs = 0
[tool.werewolf-quality.timeouts]
focus = 60
check = 180
release = 600
deep = 1200
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(quality, "REPOSITORY_ROOT", tmp_path)

    with pytest.raises(ValueError, match="max_jobs"):
        quality.load_quality_settings()


def test_default_jobs_cannot_exceed_max_jobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既定並列数を明示実行の上限内に制限する。"""
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.werewolf-quality]
benchmark_min_rounds = 5
default_jobs = 3
max_jobs = 2
[tool.werewolf-quality.timeouts]
focus = 60
check = 180
release = 600
deep = 1200
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(quality, "REPOSITORY_ROOT", tmp_path)

    with pytest.raises(ValueError, match="default_jobs"):
        quality.load_quality_settings()


def test_quality_settings_do_not_define_arbitrary_numeric_verdicts() -> None:
    """Coverageとbenchmarkは観測値とし、根拠のない閾値を持たない。"""

    document = quality._load_pyproject()
    quality_settings = document["tool"]["werewolf-quality"]
    coverage_settings = document["tool"]["coverage"]["report"]

    assert "benchmark_max_mean_ms" not in quality_settings
    assert "branch_coverage_fail_under" not in quality_settings
    assert "fail_under" not in coverage_settings


def test_profiles_have_expected_order_and_isolated_commands() -> None:
    """profileは上位になるほど前levelを包含する。"""

    focus = {gate.name for stage in quality._profile_stages("focus", 1) for gate in stage}
    check = {gate.name for stage in quality._profile_stages("check", 1) for gate in stage}
    release = {gate.name for stage in quality._profile_stages("release", 1) for gate in stage}
    deep = {gate.name for stage in quality._profile_stages("deep", 1) for gate in stage}

    assert focus < check < release < deep
    assert {"pytest", "mypy"} <= focus
    assert {"docs", "package", "integration"} <= check
    assert "coverage" not in check
    assert "benchmark" not in check
    assert "benchmark" in deep
    assert {"supabase-preflight", "supabase-lint", "supabase-integration", "docker"} <= release
    assert {"deep-tests", "deep-integration", "deep-supabase"} <= deep
    assert all(gate.command for stage in quality._profile_stages("deep", 1) for gate in stage)


def test_auto_is_an_explicit_command_separate_from_fixed_focus() -> None:
    """固定levelのFocusと差分選択を同じ名前で扱わない。"""
    parser = quality.build_parser()

    assert parser.parse_args(["auto"]).profile == "auto"
    assert parser.parse_args(["focus"]).profile == "focus"


def test_quality_cli_uses_configured_default_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """高性能hostでも通常実行は低発熱の既定並列数を使う。"""
    monkeypatch.setattr(quality.os, "cpu_count", lambda: 10)

    settings = quality.load_quality_settings()

    assert quality._default_jobs(settings) == 2
    assert quality.build_parser(settings).parse_args(["check"]).jobs == 2


def test_quality_cli_accepts_explicit_change_refs() -> None:
    """CIがbaseとsource headを品質reportへ明示できる。"""
    arguments = quality.build_parser().parse_args(
        ["check", "--base-ref", "origin/develop", "--head-ref", "feature"]
    )

    assert arguments.base_ref == "origin/develop"
    assert arguments.head_ref == "feature"


def test_repository_stability_detects_changes_after_all_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """runner終了時のsnapshot差分を品質違反として返す。"""
    (tmp_path / "logs").mkdir()
    initial = RepositorySnapshot("head", "tree", "index", False, "before")
    context = quality.RunContext(
        profile="check",
        jobs=1,
        timeout_seconds=60,
        run_id="run",
        run_dir=tmp_path,
        environment={},
        started_at=quality.utc_now(),
        initial_repository_snapshot=initial,
    )
    monkeypatch.setattr(
        quality,
        "capture_snapshot",
        lambda: RepositorySnapshot("head", "tree", "index", True, "after"),
    )

    result = quality._repository_stability_result(context)

    assert result.state == "failed"
    assert result.name == "repository-stability"


def test_explain_reports_the_plan_without_executing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """実行範囲の確認だけで品質gateを開始しない。"""
    monkeypatch.setattr(
        quality,
        "execute",
        lambda *_args, **_kwargs: pytest.fail("explain must not execute gates"),
    )

    assert quality.main(["focus", "--explain", "--jobs", "1"]) == 0
    output = capsys.readouterr().out
    assert "profile: focus" in output
    assert "再利用候補:" in output


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
    assert environment["HTTPS_PROXY"] == "https://external-proxy.example"


def test_environment_gate_classifies_blocked_executable_as_nonzero_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = SimpleNamespace(profile="focus", timeout_seconds=60, environment={})
    monkeypatch.setattr(
        environment_gate,
        "inspect_environment",
        lambda _profile: SimpleNamespace(state="passed", confirmed_causes=[]),
    )
    monkeypatch.setattr(
        environment_gate,
        "run_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("policy blocked")),
    )

    result = environment_gate.check_environment(context, tmp_path)

    assert result.returncode == 1
    assert "実行環境を起動できません" in result.output


def test_environment_gate_classifies_fingerprint_error_as_nonzero_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = SimpleNamespace(profile="focus", timeout_seconds=60, environment={})
    monkeypatch.setattr(
        environment_gate,
        "inspect_environment",
        lambda _profile: (_ for _ in ()).throw(OSError("blocked")),
    )

    result = environment_gate.check_environment(context, tmp_path)

    assert result.returncode == 1
    assert "fingerprint" in result.output


def test_quality_environment_cannot_override_isolation_invariants() -> None:
    """追加する接続情報からもsecretを除き、provider隔離を最後に強制する。"""

    environment = quality_environment(
        extra={
            "OPENAI_API_KEY": "paid-secret",  # pragma: allowlist secret
            "HTTPS_PROXY": "https://external-proxy.example",
            "WEREWOLF_LLM_PROVIDER": "openai",
            "WEREWOLF_LOCAL_LLM_BASE_URL": "http://127.0.0.1:1234/v1",
            "WEREWOLF_LOCAL_LLM_MODEL": "local-model",
            "WEREWOLF_WORKER_PAID_LLM_PROVIDER": "lmstudio",
        }
    )

    assert "OPENAI_API_KEY" not in environment
    assert environment["HTTPS_PROXY"] == "https://external-proxy.example"
    assert environment["WEREWOLF_LLM_PROVIDER"] == "fake"
    assert "WEREWOLF_LOCAL_LLM_BASE_URL" not in environment
    assert "WEREWOLF_LOCAL_LLM_MODEL" not in environment
    assert environment["WEREWOLF_WORKER_PAID_LLM_PROVIDER"] == "fake"
    assert environment["WEREWOLF_WORKER_PAID_LLM_MODEL"] == "fake-list-chat-model"
    assert environment["WEREWOLF_WORKER_PAID_LLM_BASE_URL"] == ""


def test_quality_environment_keeps_only_explicit_public_supabase_keys() -> None:
    """local E2Eに必要な公開鍵だけをsecret除外規則から外す。"""
    environment = quality_environment(
        extra={
            "OPENAI_API_KEY": "paid-secret",  # pragma: allowlist secret
            "WEREWOLF_SUPABASE_PUBLISHABLE_KEY": "local-public-key",
        }
    )

    assert "OPENAI_API_KEY" not in environment
    assert environment["WEREWOLF_SUPABASE_PUBLISHABLE_KEY"] == "local-public-key"


def test_browser_e2e_uses_the_shared_isolated_environment() -> None:
    """Streamlit E2Eへ安全な子process環境だけを渡す。"""
    source = (ROOT / "scripts" / "browser" / "e2e.py").read_text(encoding="utf-8")

    assert "quality_environment(" in source
    assert "WEREWOLF_LLM_PROVIDER" not in source
    assert '"build"' not in source
    assert '"never"' in source


def test_isolation_gate_rejects_overridden_provider_policy(tmp_path: Path) -> None:
    """子process環境のprovider隔離設定が上書きされた実行を拒否する。"""

    environment = quality_environment()
    environment["WEREWOLF_LLM_PROVIDER"] = "openai"
    context = SimpleNamespace(environment=environment)

    result = environment_gate.check_isolation_environment(context, tmp_path)

    assert result.returncode == 1
    assert "WEREWOLF_LLM_PROVIDER" in result.output


def test_redact_masks_secret_values() -> None:
    """AI向けlogにもsecretの値を残さない。"""

    output = redact("api_key=abc token:xyz role=werewolf target_id=p2 ordinary=value")

    assert "abc" not in output
    assert "xyz" not in output
    assert "werewolf" not in output
    assert "p2" not in output
    assert output.endswith("ordinary=value")


@pytest.mark.parametrize("case", REDACTION_CASES)
def test_script_redaction_matches_shared_corpus(case: dict[str, str]) -> None:
    assert redact(case["input"]) == case["expected"]


def test_redact_masks_credentials_embedded_in_url() -> None:
    """接続URLに埋め込まれたpasswordを成果物へ残さない。"""

    output = redact("dsn=postgresql://postgres:local-password@127.0.0.1:5432/postgres")

    assert "local-password" not in output
    assert output == ("dsn=postgresql://[REDACTED]@127.0.0.1:5432/postgres")


def test_redact_masks_bearer_and_query_credentials() -> None:
    output = redact(
        "Authorization: Bearer secret-value "
        "https://example.test/callback?access_token=query-secret&next=public"
    )

    assert "secret-value" not in output
    assert "query-secret" not in output
    assert "next=public" in output


def test_redact_preserves_token_usage_metrics() -> None:
    output = redact(
        'input_tokens=123 total_tokens:168 token=secret "output_tokens":45,"access_token":"private"'
    )

    assert "input_tokens=123" in output
    assert "total_tokens:168" in output
    assert '"output_tokens":45' in output
    assert "secret" not in output
    assert "private" not in output


def test_url_redaction_is_bounded_for_long_non_credential_payload() -> None:
    """生成contractの長いcurlでもcredential探索をbacktrackingさせない。"""
    started = time.monotonic()

    output = redact("http://" + "a" * 100_000 + "/openapi")

    assert output.endswith("/openapi")
    assert time.monotonic() - started < 1.0


def test_redact_artifacts_keeps_json_valid_and_masks_failure_details(
    tmp_path: Path,
) -> None:
    """失敗時のJUnitやJSONにも設定値とprivate stateを残さない。"""

    private_message = (
        "runner failed: token=private-value\nnext diagnostic"  # pragma: allowlist secret
    )
    report = tmp_path / "result.json"
    report.write_text(
        json.dumps(
            {
                "message": private_message,
                "openai_api_key": "paid-secret",  # pragma: allowlist secret
                "role": "werewolf",
                "state": "failed",
            }
        ),
        encoding="utf-8",
    )
    junit = tmp_path / "result.xml"
    junit.write_text(
        "<failure>openai_api_key=SecretStr('paid-secret'), target_id='p2'</failure>",
        encoding="utf-8",
    )

    redact_artifacts(tmp_path)

    assert json.loads(report.read_text(encoding="utf-8")) == {
        "message": "runner failed: token=[REDACTED]\nnext diagnostic",
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

    assert quality.main(["focus"]) == 2
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


def test_clean_removes_quality_reports_and_preserves_persistent_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cleanは再生成可能領域だけを削除し、実行証拠と環境状態を保持する。"""

    artifact_root = tmp_path / ".werewolf-agent"
    outputs = artifact_root / "outputs"
    cache = artifact_root / "cache"
    for path in (
        outputs,
        cache,
        artifact_root / "logs",
        artifact_root / "quality",
        artifact_root / "reviews",
        artifact_root / "runtime",
    ):
        path.mkdir(parents=True)
    temporary_root = tmp_path / "temporary" / "werewolf-agent"
    temporary_cache = temporary_root / "pytest"
    temporary_cache.mkdir(parents=True)
    monkeypatch.setattr(quality, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(
        quality,
        "BUILD_DIRECTORIES",
        (outputs, cache, artifact_root / "quality"),
    )
    monkeypatch.setattr(quality, "TEMPORARY_CACHE_DIRECTORIES", (temporary_cache,))
    monkeypatch.setattr("scripts._infra.process.ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr("scripts._infra.process.TEMPORARY_ROOT", temporary_root)

    quality.clean()

    assert not outputs.exists()
    assert not cache.exists()
    assert (artifact_root / "logs").exists()
    assert not (artifact_root / "quality").exists()
    assert (artifact_root / "reviews").exists()
    assert (artifact_root / "runtime").exists()
    assert not temporary_cache.exists()


def test_resource_cleanup_requires_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(quality.shutil, "which", lambda _command: "docker")

    def run(command: tuple[str, ...], **_kwargs: object) -> support.CommandResult:
        commands.append(tuple(command))
        return support.CommandResult(list(command), 0, 0.0, "")

    monkeypatch.setattr(quality, "run_command", run)

    assert quality.cleanup_owned_resources(confirmation=None) == 2
    assert not any("down" in command for command in commands)


def test_resource_cleanup_deletes_only_quality_owned_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(quality.shutil, "which", lambda _command: "docker")

    def run(command: tuple[str, ...], **_kwargs: object) -> support.CommandResult:
        commands.append(tuple(command))
        if command[:2] == ("docker", "ps") and any(
            "com.supabase.cli.project" in part for part in command
        ):
            output = (
                "owned-container\tquality-db\twerewolf-agent-quality-owned\n"
                "other-container\tother-db\tunrelated-project\n"
            )
        elif command[:3] == ("docker", "volume", "ls") and any(
            "com.supabase.cli.project" in part for part in command
        ):
            output = "owned-volume\twerewolf-agent-quality-owned\nother-volume\tunrelated-project\n"
        elif command[:3] == ("docker", "network", "ls"):
            output = (
                "owned-network\tquality-network\twerewolf-agent-quality-owned\n"
                "other-network\tother-network\tunrelated-project\n"
            )
        else:
            output = ""
        return support.CommandResult(list(command), 0, 0.0, output)

    monkeypatch.setattr(quality, "run_command", run)

    assert quality.cleanup_owned_resources(confirmation=quality.QUALITY_RESOURCE_CONFIRMATION) == 0
    assert any(command[:3] == ("docker", "compose", "--profile") for command in commands)
    destructive = [
        command
        for command in commands
        if command[:2] in {("docker", "rm"), ("docker", "volume"), ("docker", "network")}
        and "ls" not in command
    ]
    assert ("docker", "rm", "--force", "owned-container") in destructive
    assert ("docker", "volume", "rm", "owned-volume") in destructive
    assert ("docker", "network", "rm", "owned-network") in destructive
    assert all("other-" not in " ".join(command) for command in destructive)


@pytest.mark.parametrize(
    "arguments",
    [
        ["focus", "--jobs", "0"],
        ["focus", "--jobs", "5"],
        ["focus", "--timeout", "0"],
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
    assert Path(environment["PYTEST_DEBUG_TEMPROOT"]).is_dir()
    assert environment["PYTEST_DEBUG_TEMPROOT"] == str(tmp_path / "pytest")
    assert environment["SUPABASE_HOME"] == str(tmp_path / "supabase" / "run")


def test_artifact_root_is_repository_local() -> None:
    """生成物の既定位置を単一の管理領域へ固定する。"""

    assert ARTIFACT_ROOT.name == ".werewolf-agent"
    assert support.TEMPORARY_ROOT == ARTIFACT_ROOT / "runtime" / "tmp"


def test_branch_coverage_contract_enforces_independent_threshold(tmp_path: Path) -> None:
    """総合coverageとは別に実際のbranch rateの退行を検出する。"""

    result_path = tmp_path / "coverage.xml"
    result_path.write_text(
        '<coverage line-rate="0.75" branch-rate="0.478"/>',
        encoding="utf-8",
    )

    errors, percentage = test_gates.branch_coverage_contract(
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
            "Selected tests require --test-level=check.",
        ),
        (
            [
                "--collect-only",
                "-m",
                "monkey",
                "tests/unit/domain/test_domain_stateful.py",
            ],
            "Selected tests require --test-level=deep.",
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
    dsn = "postgresql://postgres:local-password@127.0.0.1:5432/postgres"  # pragma: allowlist secret
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


def test_nonpytest_exit_two_is_classified_as_blocked() -> None:
    result = quality.CommandResult(
        command=["environment-check"],
        returncode=2,
        duration_seconds=1.0,
        output="",
    )

    assert quality._command_state(result, nonzero_state="error") == "blocked"


def test_repository_snapshot_failure_is_not_treated_as_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Git検査失敗を空のworking treeとして扱わない。"""

    monkeypatch.setattr(
        repository_state,
        "_git_bytes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("git unavailable")),
    )

    with pytest.raises(RuntimeError, match="git unavailable"):
        repository_state.capture_snapshot()


def test_runner_setup_failure_writes_machine_readable_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gate開始前のGit検査失敗もAIが調査できる成果物へ残す。"""

    for relative in ("logs", "test-results", "coverage", "benchmarks", "browser"):
        (tmp_path / relative).mkdir()
    settings = quality.load_quality_settings()
    monkeypatch.setattr(quality, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(
        retention,
        "publish_run",
        lambda run_dir, _selector, _state: run_dir / "report.json",
    )
    monkeypatch.setattr(quality, "create_run_directory", lambda _profile: ("run", tmp_path))
    monkeypatch.setattr(quality, "quality_environment", lambda **_kwargs: {})
    monkeypatch.setattr(
        quality,
        "resolve_changes",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("git unavailable")),
    )

    state, report_path = quality.execute(
        "focus",
        jobs=1,
        timeout_seconds=1,
        settings=settings,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert state == "error"
    assert report["state"] == "error"
    assert report["results"][0]["name"] == "runner-setup"
    assert any(result["state"] == "skipped" for result in report["results"])
    assert (report_path.parent / "logs" / "runner-setup.log").is_file()


def test_vscode_and_ci_use_the_shared_quality_entrypoint() -> None:
    """利用場所ごとに独自の品質判定経路を作らない。"""

    launch = json.loads((ROOT / ".vscode" / "launch.json").read_text(encoding="utf-8"))
    tasks = json.loads((ROOT / ".vscode" / "tasks.json").read_text(encoding="utf-8"))
    settings = json.loads((ROOT / ".vscode" / "settings.json").read_text(encoding="utf-8"))
    extensions = json.loads((ROOT / ".vscode" / "extensions.json").read_text(encoding="utf-8"))
    visible_launch_names = {
        configuration["name"]
        for configuration in launch["configurations"]
        if not configuration.get("presentation", {}).get("hidden", False)
    }
    visible_task_names = {task["label"] for task in tasks["tasks"] if not task.get("hide", False)}
    task_commands = {
        task["label"]: task.get("args", [])
        for task in tasks["tasks"]
        if task.get("type") == "process"
    }
    workflow = (ROOT / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8") + (
        ROOT / ".github" / "actions" / "deep-readiness" / "action.yml"
    ).read_text(encoding="utf-8")

    assert visible_launch_names == {"クライアント: Streamlit", "クライアント: CLI Play"}
    assert visible_task_names == {
        "環境: Pythonを準備",
        "環境: 開発環境を準備",
        "環境: 品質環境を準備",
        "環境: 状態を確認",
        "品質: Auto",
        "品質: Focus",
        "品質: Check",
        "品質: Release",
        "品質: Deep",
        "品質: 最新Reportを開く",
        "品質: 生成物を削除",
        "品質: 所有Resourcesを削除",
        "レビュー: UI",
        "レビュー: Gameplay",
        "レビュー: Local LLM",
        "診断: 情報を収集",
    }
    compounds = {compound["name"]: compound for compound in launch["compounds"]}
    assert set(compounds) == {
        "開発: Full Stack",
        "開発: Backend",
        "デバッグ: API",
        "デバッグ: Worker",
    }
    assert all(
        "内部: Supabase" in compound["configurations"]
        and compound["stopAll"] is True
        and compound["preLaunchTask"].endswith("を予約")
        for compound in compounds.values()
    )
    assert "Internal: Supabase Preflight" not in task_commands
    assert task_commands["内部: Supabaseの準備完了を待つ"][-4:] == [
        "scripts.supabase",
        "wait",
        "--timeout",
        "180",
    ]
    supabase_launch = next(
        configuration
        for configuration in launch["configurations"]
        if configuration["name"] == "内部: Supabase"
    )
    assert supabase_launch["postDebugTask"] == "内部: Supabaseセッションを停止"
    assert task_commands["内部: Supabaseセッションを停止"][-2:] == [
        "scripts.supabase",
        "stop-session",
    ]
    stack_configurations = {
        configuration["name"]: configuration
        for configuration in launch["configurations"]
        if configuration["name"] in {"内部: API", "内部: Worker", "内部: Full Stack Streamlit"}
    }
    assert set(stack_configurations) == {
        "内部: API",
        "内部: Worker",
        "内部: Full Stack Streamlit",
    }
    assert all(
        configuration["preLaunchTask"] == "内部: Supabaseの準備完了を待つ"
        for configuration in stack_configurations.values()
    )
    assert set(compounds["開発: Full Stack"]["configurations"]) == {
        "内部: Supabase",
        *stack_configurations,
    }
    assert "inputs" not in launch
    streamlit_configurations = [
        configuration
        for configuration in launch["configurations"]
        if "Streamlit" in configuration["name"]
    ]
    assert all(
        configuration["serverReadyAction"]["pattern"] == r"(?:Local )?URL: (https?://[^\s]+)"
        for configuration in streamlit_configurations
    )
    assert "promptString" not in json.dumps(launch)
    cleanup_input = next(
        item for item in tasks["inputs"] if item["id"] == "qualityResourceCleanupConfirmation"
    )
    assert cleanup_input["type"] == "promptString"
    assert "DELETE" in cleanup_input["description"]
    assert task_commands["品質: 所有Resourcesを削除"][-2:] == [
        "--confirm",
        "${input:qualityResourceCleanupConfirmation}",
    ]
    assert task_commands["品質: Auto"][-4:] == ["python", "-m", "scripts.quality", "auto"]
    assert task_commands["品質: Focus"][-4:] == ["python", "-m", "scripts.quality", "focus"]
    assert task_commands["品質: Check"][-4:] == ["python", "-m", "scripts.quality", "check"]
    assert task_commands["環境: Pythonを準備"][-1] == "python"
    assert task_commands["環境: 開発環境を準備"][-1] == "development"
    assert task_commands["環境: 品質環境を準備"][-1] == "quality"
    assert all(
        "dependsOn" not in task for task in tasks["tasks"] if task["label"].startswith("品質:")
    )
    assert "scripts.workbench" not in json.dumps(launch) + json.dumps(tasks)
    assert "PYTHONPATH" not in json.dumps(launch)
    assert "python -m scripts.quality check" in workflow
    assert "python -m scripts.quality release" not in workflow
    assert "python -m scripts.quality deep" in workflow
    assert "--confirm-deep" in workflow
    assert 'python-version: ["3.11", "3.13", "3.14"]' in workflow
    assert "--base-ref origin/develop" in workflow
    assert "base-ref: origin/main" in workflow
    assert "actions/upload-artifact@" in workflow
    assert "include-hidden-files: true" in workflow
    assert ".werewolf-agent/outputs" not in workflow
    assert ".werewolf-agent/operations" not in workflow
    assert not (ROOT / ".github" / "workflows" / "docker.yml").exists()
    assert settings["python.testing.pytestArgs"] == ["--test-level=focus", "tests/unit"]
    assert "flake8.enabled" not in settings
    assert "isort.serverEnabled" not in settings
    assert "ms-python.mypy-type-checker" in extensions["recommendations"]


def test_runtime_docker_dependencies_are_cached_before_source_copy() -> None:
    """Releaseは事前構築済みの現行runtime imageだけを検査する。"""

    backend = (ROOT / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")

    assert "FROM runtime-dependencies AS runtime" in backend
    assert "USER app" in backend
    commands = runtime.docker_commands("quality:test")
    assert len(commands) == 3
    assert all("--network" in command and "none" in command for command in commands)
    assert "os.geteuid() != 0" in commands[0][-1]
    assert commands[1][-2:] == ["quality:test", "--help"]
    assert "werewolf-agent-worker" in commands[1]
    assert "werewolf-agent" in commands[2]
