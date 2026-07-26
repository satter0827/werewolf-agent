"""Deterministic random-source derivation for game commands."""

RUNTIME_SEED_VERSION_FACTOR = 1009


def runtime_seed(seed: int | None, version: int) -> int:
    """Derive one deterministic seed for an aggregate version."""
    return (seed or 0) + version * RUNTIME_SEED_VERSION_FACTOR


__all__ = ["runtime_seed"]
