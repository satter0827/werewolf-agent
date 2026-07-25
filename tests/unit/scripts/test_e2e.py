"""container E2E orchestrationの安全境界を検査する。"""

from pathlib import Path

import pytest
from scripts import e2e
from scripts._support import EnvironmentBlockedError


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
    assert environment["PLAYWRIGHT_VISUAL_REGRESSION"] == "1"


def test_commands_never_build_or_pull_images(tmp_path: Path) -> None:
    """runner内のE2Eは事前構築済みimageだけを使用する。"""
    commands = e2e._commands(tmp_path)
    flattened = " ".join(part for command in commands for part in command)

    assert "--pull never" in flattened
    assert " build " not in f" {flattened} "
    assert str(tmp_path.resolve()) in flattened


def test_playwright_blocks_nonlocal_browser_requests() -> None:
    """画面testからlocal service以外へのrequestを失敗させる。"""
    fixture = (Path(__file__).resolve().parents[3] / "frontend" / "e2e" / "fixtures.ts").read_text(
        encoding="utf-8"
    )

    assert 'page.route("**/*"' in fixture
    assert "route.abort" in fixture
    assert "host.docker.internal" in fixture
    assert "blockedHosts" in fixture


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
