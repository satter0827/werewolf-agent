"""Deterministic random-source derivation for game commands."""

from werewolf_agent.setup import namespace_seed

RUNTIME_SEED_VERSION_FACTOR = 1009


def runtime_seed(seed: int | None, version: int) -> int:
    """Derive one deterministic seed for an aggregate version."""
    return namespace_seed(seed or 0, "gameplay") + version * RUNTIME_SEED_VERSION_FACTOR


__all__ = ["runtime_seed"]
