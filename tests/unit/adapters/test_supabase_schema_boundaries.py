"""Supabase schemaの公開範囲。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "supabase" / "migrations" / "20260729082649_release_0_1_0_baseline.sql"


def _baseline() -> str:
    return BASELINE.read_text(encoding="utf-8").casefold()


def test_release_0_1_0_uses_one_from_scratch_baseline() -> None:
    """pre-release migration履歴を配布contractへ残さない。"""
    migrations = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))

    assert migrations == [BASELINE]
    assert "does not upgrade pre-release data" in _baseline()


def test_private_supabase_projections_are_not_data_api_tables() -> None:
    migration = _baseline()

    for table in ("game_player_observations", "game_reveals"):
        assert f'create table if not exists "private"."{table}"' in migration
    assert 'revoke all on all tables in schema "private" from "anon", "authenticated"' in migration


def test_game_tables_are_unavailable_through_supabase_data_api() -> None:
    migration = _baseline()

    for table in (
        "games",
        "game_summaries",
        "game_participants",
        "game_public_turns",
        "game_operation_requests",
    ):
        assert f'create table if not exists "public"."{table}"' in migration
    assert 'revoke all on all tables in schema "public" from "anon", "authenticated"' in migration
    for legacy_name in ("definition_items", "profiles", "retention_runs", "user_preferences"):
        assert f'"public"."{legacy_name}"' not in migration


def test_baseline_owns_pgmq_and_private_snapshot_state() -> None:
    migration = _baseline()

    assert 'create extension if not exists "pgmq"' in migration
    assert 'create table if not exists "private"."game_snapshots"' in migration
    assert 'select "pgmq"."create"(\'game_operations\')' in migration


def test_user_setup_revisions_are_private_immutable_and_semver_versioned() -> None:
    migration = _baseline()

    assert 'create table if not exists "private"."user_setups"' in migration
    assert 'create table if not exists "private"."user_setup_revisions"' in migration
    assert '"schema_version" "text" not null' in migration
    assert "'0.5.0'" in migration
    assert (
        'grant select,insert on table "private"."user_setup_revisions" to "service_role"'
        in migration
    )
    assert 'grant update on table "private"."user_setup_revisions"' not in migration


def test_baseline_has_no_redundant_engine_or_definition_version_columns() -> None:
    migration = _baseline()

    assert "engine_version" not in migration
    assert "definition_snapshot" not in migration
