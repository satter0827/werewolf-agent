"""container E2E orchestrationの安全境界を検査する。"""

from pathlib import Path

import pytest
from scripts._infra.process import EnvironmentBlockedError
from scripts.browser import e2e
from scripts.browser.scenarios.quality import FORBIDDEN_INTERNAL_TERMS
from scripts.quality.gates import browser as browser_gate


def _environment() -> dict[str, str]:
    return {
        "WEREWOLF_SUPABASE_DB_DSN": "postgresql://postgres:local@127.0.0.1:54322/postgres",
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


def test_e2e_image_installs_browser_before_source_and_excludes_code_tests() -> None:
    """Browser取得layerをsource変更から分離し、品質scenarioだけを同梱する。"""
    dockerfile = (Path(__file__).resolve().parents[3] / "docker" / "e2e.Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "--no-install-project" in dockerfile
    assert dockerfile.index("playwright install") < dockerfile.index("COPY src")
    assert "COPY tests" not in dockerfile


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
