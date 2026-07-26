"""並列修正可能なintegration testの責務配置。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INTEGRATION_AREAS = frozenset({"api", "worker", "clients", "supabase", "package"})


def test_integration_tests_are_partitioned_by_runtime_boundary() -> None:
    root = ROOT / "tests" / "integration"

    assert {path.name for path in root.iterdir() if path.is_dir()} == INTEGRATION_AREAS
    assert not list(root.glob("test_*.py"))
    assert all(list((root / area).glob("test_*.py")) for area in INTEGRATION_AREAS)
