"""Deterministic random-source derivation for game commands."""

import hashlib

RUNTIME_SEED_VERSION_FACTOR = 1009


def runtime_seed(seed: int | None, version: int) -> int:
    """Derive one deterministic seed for an aggregate version."""
    return namespace_seed(seed or 0, "gameplay") + version * RUNTIME_SEED_VERSION_FACTOR


def namespace_seed(seed: int, namespace: str) -> int:
    """Derive an isolated deterministic seed using a stable namespace."""
    digest = hashlib.sha256(f"werewolf-agent:v2:{seed}:{namespace}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


__all__ = ["namespace_seed", "runtime_seed"]
