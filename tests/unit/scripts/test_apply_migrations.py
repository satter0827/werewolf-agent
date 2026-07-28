from pathlib import Path

import pytest
from scripts.supabase.migrations import _migration_identity


def test_migration_identity_uses_supabase_version_and_name() -> None:
    assert _migration_identity(Path("20260724000000_second_stage_baseline.sql")) == (
        "20260724000000",
        "second_stage_baseline",
    )


def test_migration_identity_rejects_noncanonical_names() -> None:
    with pytest.raises(ValueError, match="Invalid Supabase migration"):
        _migration_identity(Path("second_stage.sql"))
