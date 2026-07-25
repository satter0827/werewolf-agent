"""Supabase事前確認の純粋処理を検査する。"""

import re
from pathlib import Path

import pytest
from scripts.supabase import preflight as preflight_supabase
from scripts.supabase.preflight import (
    is_supported_supabase_version,
    parse_status_environment,
    select_status_environment,
)


def test_supabase_cli_version_is_pinned() -> None:
    """Image構成と異なるSupabase CLIで品質実行を開始しない。"""

    assert is_supported_supabase_version("2.104.0\n")
    assert not is_supported_supabase_version("2.105.0\n")


@pytest.mark.parametrize("value", ["0", "-1"])
def test_preflight_rejects_non_positive_timeout(value: str) -> None:
    """不正なtimeoutを外部process起動前に拒否する。"""

    with pytest.raises(SystemExit) as captured:
        preflight_supabase.build_parser().parse_args(["--timeout", value])

    assert captured.value.code == 2


def test_parse_status_environment_accepts_only_env_assignments() -> None:
    """CLIの補足文を接続環境へ混入させない。"""

    output = "\n".join(
        [
            'API_URL="http://127.0.0.1:54321"',
            'PUBLISHABLE_KEY="local-key"',
            'SERVICE_ROLE_KEY="must-not-leak"',
            "Stopped services: analytics",
            'DB_URL="postgresql://postgres:local@127.0.0.1:54322/postgres"',
        ]
    )

    assert parse_status_environment(output) == {
        "API_URL": "http://127.0.0.1:54321",
        "PUBLISHABLE_KEY": "local-key",
        "SERVICE_ROLE_KEY": "must-not-leak",
        "DB_URL": "postgresql://postgres:local@127.0.0.1:54322/postgres",
    }
    assert select_status_environment(output) == {
        "API_URL": "http://127.0.0.1:54321",
        "PUBLISHABLE_KEY": "local-key",
        "DB_URL": "postgresql://postgres:local@127.0.0.1:54322/postgres",
    }


def test_isolated_project_uses_distinct_project_id_and_ports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """品質用Supabaseを開発用projectと同じcontainerへ接続させない。"""

    repository = tmp_path / "repository"
    source = repository / "supabase"
    (source / "migrations").mkdir(parents=True)
    (source / "migrations" / "001.sql").write_text("select 1;\n", encoding="utf-8")
    (source / "config.toml").write_text(
        'project_id = "development"\n[api]\nport = 54321\n[db]\nport = 54322\n',
        encoding="utf-8",
    )
    artifact_root = repository / ".werewolf-agent"
    isolated_root = artifact_root / "db" / "quality" / "run-1"
    monkeypatch.setattr(preflight_supabase, "REPOSITORY_ROOT", repository)
    monkeypatch.setattr("scripts._infra.process.ARTIFACT_ROOT", artifact_root)

    workdir, project_id = preflight_supabase._prepare_isolated_project(isolated_root)

    config = (workdir / "supabase" / "config.toml").read_text(encoding="utf-8")
    ports = [int(port) for port in re.findall(r"^port = (\d+)$", config, re.MULTILINE)]
    assert project_id == preflight_supabase.isolated_project_id(isolated_root)
    assert 'project_id = "development"' not in config
    assert len(ports) == len(set(ports)) == 2
    assert set(ports).isdisjoint({54321, 54322})
    assert (workdir / "supabase" / "migrations" / "001.sql").is_file()

    second_root = artifact_root / "db" / "quality" / "run-2"
    _, second_project_id = preflight_supabase._prepare_isolated_project(second_root)
    assert second_project_id != project_id
