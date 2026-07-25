import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "apply_migrations.py"
SPEC = importlib.util.spec_from_file_location("apply_migrations", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
_migration_identity = MODULE._migration_identity


def test_migration_identity_uses_supabase_version_and_name() -> None:
    assert _migration_identity(Path("20260724000000_second_stage_baseline.sql")) == (
        "20260724000000",
        "second_stage_baseline",
    )


def test_migration_identity_rejects_noncanonical_names() -> None:
    with pytest.raises(ValueError, match="Invalid Supabase migration"):
        _migration_identity(Path("second_stage.sql"))
