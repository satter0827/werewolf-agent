"""Business identifier normalization owned by the application layer."""

PLAYER_NUMBER_START = 1


def non_blank(value: str, field_name: str) -> str:
    """Normalize and require one nonblank application string."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def generated_player_id(index: int) -> str:
    """Return the canonical generated player ID for a one-based index."""
    if index < PLAYER_NUMBER_START:
        raise ValueError("generated player index must be at least 1")
    return f"p{index}"


def generated_player_ids(player_count: int) -> set[str]:
    """Return all canonical generated player IDs for a standard game."""
    if player_count < PLAYER_NUMBER_START:
        return set()
    return {generated_player_id(index) for index in range(PLAYER_NUMBER_START, player_count + 1)}


def public_generated_player_label(value: object) -> str | None:
    """Return a compact public label for a canonical generated player ID."""
    text = str(value)
    if not text.startswith("p"):
        return None
    suffix = text.removeprefix("p")
    return f"P{suffix}" if suffix.isdigit() else None


__all__ = [
    "generated_player_id",
    "generated_player_ids",
    "non_blank",
    "public_generated_player_label",
]
