"""用途ごとに分離した決定的seedを生成する."""

import hashlib


def namespace_seed(seed: int, namespace: str) -> int:
    """安定したnamespaceから独立した決定的seedを返す."""
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise TypeError("seed must be an integer")
    normalized = namespace.strip()
    if not normalized:
        raise ValueError("namespace must not be blank")
    digest = hashlib.sha256(f"werewolf-agent:v2:{seed}:{normalized}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


__all__ = ["namespace_seed"]
