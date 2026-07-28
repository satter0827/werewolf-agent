"""Supabase schemaの公開範囲。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src" / "werewolf_agent"


def test_private_supabase_projections_are_not_data_api_tables() -> None:
    migration = (
        ROOT / "supabase" / "migrations" / "20260724000000_second_stage_baseline.sql"
    ).read_text(encoding="utf-8")
    for table in ("game_player_observations", "game_reveals"):
        assert f"alter table public.{table} set schema private" in migration
    assert "revoke all on all tables in schema private from anon, authenticated" in migration


def test_game_tables_are_unavailable_through_supabase_data_api() -> None:
    migration = (
        ROOT / "supabase" / "migrations" / "20260724000000_second_stage_baseline.sql"
    ).read_text(encoding="utf-8")
    for table in (
        "games",
        "game_summaries",
        "game_participants",
        "game_public_turns",
        "game_operation_requests",
    ):
        assert f"revoke all on public.{table} from anon, authenticated" in migration
    cleanup_migration = (
        ROOT / "supabase" / "migrations" / "20260725000000_remove_legacy_public_tables.sql"
    ).read_text(encoding="utf-8")
    for legacy_table in (
        "profiles",
        "user_preferences",
        "definition_items",
        "retention_runs",
    ):
        assert f"drop table if exists public.{legacy_table}" in cleanup_migration
    rpc_cleanup = (
        ROOT / "supabase" / "migrations" / "20260725010000_remove_legacy_public_rpc.sql"
    ).read_text(encoding="utf-8")
    assert "drop function if exists public.is_admin() cascade" in rpc_cleanup
    for private_replacement in ("llm_invocations", "audit_events"):
        assert f"drop table if exists public.{private_replacement}" in migration


def test_agent_graph_cleanup_updates_the_private_snapshot_owner() -> None:
    migration = (
        ROOT / "supabase" / "migrations" / "20260726000000_adopt_pgmq_and_single_agent_graph.sql"
    ).read_text(encoding="utf-8")

    assert "update private.game_snapshots\nset config" in migration
    assert "update public.games\nset config" not in migration


def test_user_setup_revisions_are_private_immutable_and_owner_indexed() -> None:
    migration = (
        ROOT / "supabase" / "migrations" / "20260727085037_add_user_setup_revisions.sql"
    ).read_text(encoding="utf-8")

    assert "create table private.user_setups" in migration
    assert "create table private.user_setup_revisions" in migration
    assert "primary key (setup_id, revision)" in migration
    assert "on private.user_setups (owner_user_id, created_at desc)" in migration
    assert "(select auth.uid()) = owner_user_id" in migration
    assert "revoke all on private.user_setups from anon, authenticated" in migration
    assert "revoke all on private.user_setup_revisions from anon, authenticated" in migration
    assert "grant select, insert on private.user_setup_revisions to service_role" in migration
    assert "grant update" not in migration


def test_complete_setup_document_replaces_the_legacy_definition_snapshot_column() -> None:
    migration = (
        ROOT / "supabase" / "migrations" / "20260727104335_remove_definition_snapshot.sql"
    ).read_text(encoding="utf-8")

    assert "alter table public.games" in migration
    assert "drop column definition_snapshot" in migration
