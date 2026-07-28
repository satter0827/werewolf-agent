"""Structural contract between OpenAPI and Python client surfaces."""

from werewolf_agent.api.bootstrap import create_app
from werewolf_agent.clients.cli.app import CLI_COMMAND_IMPLEMENTATIONS
from werewolf_agent.clients.presentation import (
    CLI_COMMAND_FEATURES,
    FEATURES,
    STREAMLIT_WORKSPACE_FEATURES,
    implemented_feature_ids,
)
from werewolf_agent.clients.streamlit.feature_implementations import (
    STREAMLIT_FEATURE_IMPLEMENTATIONS,
)
from werewolf_agent.settings import AppSettings


def _operation_ids() -> list[str]:
    schema = create_app(AppSettings(_env_file=None)).openapi()
    return [
        operation["operationId"]
        for path in schema["paths"].values()
        for method, operation in path.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]


def test_openapi_operation_ids_are_explicit_unique_and_classified() -> None:
    operation_ids = _operation_ids()
    assert len(operation_ids) == len(set(operation_ids))
    assert set(operation_ids) == set(FEATURES)


def test_required_python_client_features_have_placements() -> None:
    cli = [item for values in CLI_COMMAND_FEATURES.values() for item in values]
    streamlit = [item for values in STREAMLIT_WORKSPACE_FEATURES.values() for item in values]
    for feature_id, feature in FEATURES.items():
        assert cli.count(feature_id) >= int(feature.cli_required), feature_id
        assert streamlit.count(feature_id) >= int(feature.streamlit_required), feature_id
    assert all(len(values) == len(set(values)) for values in CLI_COMMAND_FEATURES.values())
    assert all(len(values) == len(set(values)) for values in STREAMLIT_WORKSPACE_FEATURES.values())
    assert set(cli) <= set(FEATURES)
    assert set(streamlit) <= set(FEATURES)


def test_admin_features_are_not_bound_to_normal_game_workspaces() -> None:
    admin_ids = {key for key, value in FEATURES.items() if value.audience == "admin"}
    for workspace, feature_ids in STREAMLIT_WORKSPACE_FEATURES.items():
        if workspace != "admin":
            assert admin_ids.isdisjoint(feature_ids)


def test_cli_feature_bindings_are_attached_to_registered_commands() -> None:
    assert set(CLI_COMMAND_IMPLEMENTATIONS) == set(CLI_COMMAND_FEATURES)
    for path, implementation in CLI_COMMAND_IMPLEMENTATIONS.items():
        assert implemented_feature_ids(implementation) == CLI_COMMAND_FEATURES[path]


def test_streamlit_renderers_declare_every_bound_feature() -> None:
    declared = {
        feature_id
        for implementation in STREAMLIT_FEATURE_IMPLEMENTATIONS.values()
        for feature_id in implemented_feature_ids(implementation)
    }
    placed = {
        feature_id
        for feature_ids in STREAMLIT_WORKSPACE_FEATURES.values()
        for feature_id in feature_ids
    }
    assert declared == placed
