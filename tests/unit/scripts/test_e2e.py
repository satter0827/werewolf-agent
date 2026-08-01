"""container E2E orchestrationの安全境界を検査する。"""

import json
from pathlib import Path

import pytest
from scripts._infra.process import EnvironmentBlockedError
from scripts.browser import e2e
from scripts.browser.scenarios.quality import FORBIDDEN_INTERNAL_TERMS
from scripts.quality.gates import browser as browser_gate

LOCAL_DATABASE_DSN = (
    "postgresql://postgres:local@127.0.0.1:54322/postgres"  # pragma: allowlist secret
)


def _environment() -> dict[str, str]:
    return {
        "WEREWOLF_SUPABASE_DB_DSN": LOCAL_DATABASE_DSN,
        "WEREWOLF_SUPABASE_PUBLISHABLE_KEY": "local-public-key",
        "WEREWOLF_SUPABASE_URL": "http://127.0.0.1:54321",
    }


def test_compose_environment_uses_container_hosts_and_fake_provider() -> None:
    """host接続値だけをcontainer向けに変換し、有料providerを無効化する。"""
    environment = e2e._compose_environment(_environment(), visual_regression=True)

    assert "host.docker.internal:54321" in environment["WEREWOLF_SUPABASE_URL"]
    assert "host.docker.internal:54322" in environment["WEREWOLF_COMPOSE_SUPABASE_DB_DSN"]
    assert environment["WEREWOLF_LLM_PROVIDER"] == "fake"
    assert environment["WEREWOLF_API_RATE_LIMIT_REQUESTS"] == "10000"
    assert environment["PLAYWRIGHT_VISUAL_REGRESSION"] == "1"


def test_commands_never_build_or_pull_images(tmp_path: Path) -> None:
    """runner内のE2Eは事前構築済みimageだけを使用する。"""
    commands = e2e._commands(tmp_path)
    flattened = " ".join(part for command in commands for part in command)

    assert "--pull never" in flattened
    assert " build " not in f" {flattened} "
    assert str(tmp_path.resolve()) in flattened


def test_container_artifact_ownership_is_restored_to_posix_host_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """container成果物をredaction前にhost利用者へ返す。"""
    recorded: list[list[str]] = []

    def successful(command: list[str], **_kwargs: object) -> e2e.CommandResult:
        recorded.append(command)
        return e2e.CommandResult(command, 0, 0.1, "")

    monkeypatch.setattr(e2e, "_host_identity", lambda: (1001, 127))
    monkeypatch.setattr(e2e, "run_command", successful)

    result = e2e.restore_container_artifact_ownership(tmp_path, environment={})

    assert result.returncode == 0
    assert recorded[0][-4:] == [
        "chown",
        "-R",
        "1001:127",
        "/tmp/werewolf-agent/playwright",
    ]
    assert f"{tmp_path.resolve()}:/tmp/werewolf-agent/playwright" in recorded[0]


def test_container_artifact_ownership_is_a_noop_without_posix_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows hostではDocker Desktopの所有権変換に介入しない。"""
    monkeypatch.setattr(e2e, "_host_identity", lambda: None)
    monkeypatch.setattr(
        e2e,
        "run_command",
        lambda *_args, **_kwargs: pytest.fail("dockerを実行してはいけません"),
    )

    result = e2e.restore_container_artifact_ownership(tmp_path, environment={})

    assert result.returncode == 0


def test_e2e_image_contains_only_stable_dependencies_and_mounts_current_source() -> None:
    """Browser依存imageをsource変更から分離し、現在sourceをreadonlyで検査する。"""
    root = Path(__file__).resolve().parents[3]
    dockerfile = (root / "docker" / "e2e.Dockerfile").read_text(encoding="utf-8")
    compose = (root / "compose.yaml").read_text(encoding="utf-8")

    assert "--no-install-project" in dockerfile
    assert "playwright install" in dockerfile
    assert "COPY src" not in dockerfile
    assert "COPY scripts" not in dockerfile
    assert "COPY tests" not in dockerfile
    assert ".:/workspace:ro" in compose


def test_browser_gate_declares_public_contact_sheet() -> None:
    """一覧画像をprivate成果物と混在しない公開pathで要求する。"""
    gate = browser_gate.build()[0]

    assert "browser/public/contact-sheet.png" in gate.artifacts
    assert "browser/contact-sheet.png" not in gate.artifacts


def test_playwright_blocks_nonlocal_browser_requests() -> None:
    """画面testからlocal service以外へのrequestを失敗させる。"""
    fixture = (
        Path(__file__).resolve().parents[3] / "scripts" / "browser" / "scenarios" / "conftest.py"
    ).read_text(encoding="utf-8")

    assert 'page.route("**/*"' in fixture
    assert 'route.abort("blockedbyclient")' in fixture
    assert "host.docker.internal" in fixture
    assert "blocked_hosts" in fixture


def test_streamlit_scenarios_do_not_scroll_rerendered_controls() -> None:
    """full-page取得では再描画中の要素handleへscroll操作を行わない。"""
    root = Path(__file__).resolve().parents[3] / "scripts" / "browser" / "scenarios"
    scenarios = (root / "test_streamlit.py").read_text(encoding="utf-8")
    fixture = (root / "conftest.py").read_text(encoding="utf-8")

    assert "scroll_into_view_if_needed" not in scenarios
    assert "full_page=True" in fixture


def test_internal_term_pattern_rejects_terms_without_matching_identifiers() -> None:
    """内部用語は単語として拒否し、UUIDやemailの一部を誤検知しない。"""
    assert FORBIDDEN_INTERNAL_TERMS.search("API provider")
    assert not FORBIDDEN_INTERNAL_TERMS.search("streamlit-e2e-2dbf@example.com")


def test_run_e2e_rejects_missing_local_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Supabase設定不足時はcontainerを起動しない。"""
    monkeypatch.setattr(e2e.shutil, "which", lambda _name: "docker")

    with pytest.raises(EnvironmentBlockedError, match="Supabase設定"):
        e2e.run_e2e(
            base_environment={},
            artifact_directory=tmp_path,
            timeout_seconds=30,
            visual_regression=False,
        )


def test_owned_resource_snapshot_rejects_failed_docker_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Docker列挙失敗をresourceなしとして誤成功させない。"""

    def failed(command: list[str], **_kwargs: object) -> e2e.CommandResult:
        return e2e.CommandResult(command, 1, 0.0, "daemon unavailable")

    monkeypatch.setattr(e2e, "run_command", failed)

    with pytest.raises(EnvironmentBlockedError, match="確認できません"):
        e2e._owned_resource_snapshot({})


def test_browser_cli_publishes_a_completed_review_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review = tmp_path / "browser-run"
    monkeypatch.setattr(
        e2e,
        "run_e2e",
        lambda **_kwargs: e2e.CommandResult(["pytest"], 0, 0.1, "passed\n"),
    )
    monkeypatch.setattr(e2e, "prune_review_runs", lambda: None)

    result = e2e.main(["--artifacts", str(review), "--timeout", "1"])

    assert result == 0
    assert not (review / ".active").exists()
    assert {"report.json", "summary.md", "manifest.json"}.issubset(
        {path.name for path in review.iterdir()}
    )
    report = json.loads((review / "report.json").read_text(encoding="utf-8"))
    assert report["state"] == "passed"
