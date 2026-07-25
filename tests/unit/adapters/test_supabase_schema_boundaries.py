"""Supabase schemaの公開範囲。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src" / "werewolf_agent"
FRONTEND = ROOT / "frontend" / "src"


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
