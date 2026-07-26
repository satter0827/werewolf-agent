"""Small, explicit catalog of user-facing HTTP operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Literal, TypeVar, cast

FeatureAudience = Literal["public", "player", "admin"]
FeatureDependency = Literal["api", "authentication", "database", "operation_queue"]
ReactStatus = Literal["implemented", "deferred"]
TCallable = TypeVar("TCallable", bound=Callable[..., Any])
FEATURE_IDS_ATTRIBUTE: Final = "__werewolf_feature_ids__"


@dataclass(frozen=True)
class FeatureSpec:
    """Describe one user-facing operation without owning its behavior."""

    operation_id: str
    audience: FeatureAudience
    dependencies: tuple[FeatureDependency, ...]
    cli_required: bool = True
    streamlit_required: bool = True
    react_status: ReactStatus = "deferred"


_FEATURES: Final[tuple[FeatureSpec, ...]] = (
    FeatureSpec("runtime_config_get", "public", ("api",)),
    FeatureSpec("runtime_status_get", "public", ("api",)),
    FeatureSpec(
        "session_get",
        "player",
        ("api", "authentication"),
        cli_required=False,
    ),
    FeatureSpec("game_create", "player", ("api", "authentication", "database", "operation_queue")),
    FeatureSpec("game_list", "player", ("api", "authentication", "database")),
    FeatureSpec("game_get", "player", ("api", "authentication", "database")),
    FeatureSpec("game_timeline_get", "player", ("api", "authentication", "database")),
    FeatureSpec("game_observation_get", "player", ("api", "authentication", "database")),
    FeatureSpec(
        "game_action_submit",
        "player",
        ("api", "authentication", "database", "operation_queue"),
    ),
    FeatureSpec(
        "game_advance",
        "player",
        ("api", "authentication", "database", "operation_queue"),
    ),
    FeatureSpec("operation_get", "player", ("api", "authentication", "database")),
    FeatureSpec("admin_game_reveal", "admin", ("api", "authentication", "database")),
    FeatureSpec("admin_replay_verify", "admin", ("api", "authentication", "database")),
    FeatureSpec("admin_operation_get", "admin", ("api", "authentication", "database")),
    FeatureSpec("admin_llm_traces_get", "admin", ("api", "authentication", "database")),
    FeatureSpec("admin_llm_usage_get", "admin", ("api", "authentication", "database")),
)

FEATURES: Final[dict[str, FeatureSpec]] = {feature.operation_id: feature for feature in _FEATURES}


def feature_ids() -> frozenset[str]:
    """Return every stable user-facing operation id."""
    return frozenset(FEATURES)


def implements_features(*operation_ids: str) -> Callable[[TCallable], TCallable]:
    """Declare the API features implemented by one concrete command or renderer."""
    unknown = set(operation_ids) - feature_ids()
    if unknown:
        raise ValueError(f"unknown feature ids: {', '.join(sorted(unknown))}")
    if len(operation_ids) != len(set(operation_ids)):
        raise ValueError("feature ids must not be duplicated")

    def decorate(target: TCallable) -> TCallable:
        setattr(target, FEATURE_IDS_ATTRIBUTE, tuple(operation_ids))
        return target

    return decorate


def implemented_feature_ids(target: Callable[..., Any]) -> tuple[str, ...]:
    """Return the feature declaration attached to a concrete implementation."""
    return cast(tuple[str, ...], getattr(target, FEATURE_IDS_ATTRIBUTE, ()))


__all__ = [
    "FEATURES",
    "FeatureAudience",
    "FeatureDependency",
    "FeatureSpec",
    "feature_ids",
    "implemented_feature_ids",
    "implements_features",
]
