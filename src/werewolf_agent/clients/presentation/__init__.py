"""Presentation contracts shared by human-facing clients."""

from werewolf_agent.clients.presentation.bindings import (
    CLI_COMMAND_FEATURES,
    STREAMLIT_WORKSPACE_FEATURES,
)
from werewolf_agent.clients.presentation.errors import ErrorPresentation, present_error
from werewolf_agent.clients.presentation.features import (
    FEATURES,
    FeatureAudience,
    FeatureDependency,
    FeatureSpec,
    feature_ids,
    implemented_feature_ids,
    implements_features,
)

__all__ = [
    "CLI_COMMAND_FEATURES",
    "FEATURES",
    "STREAMLIT_WORKSPACE_FEATURES",
    "ErrorPresentation",
    "FeatureAudience",
    "FeatureDependency",
    "FeatureSpec",
    "feature_ids",
    "implemented_feature_ids",
    "implements_features",
    "present_error",
]
