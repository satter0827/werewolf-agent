"""Declarative placement of API features in Python client surfaces."""

CLI_COMMAND_FEATURES: dict[str, tuple[str, ...]] = {
    "system status": ("runtime_status_get",),
    "setup show": ("runtime_config_get",),
    "setup validate": ("setup_validate",),
    "setup inspect": ("setup_validate",),
    "game create": ("game_create",),
    "game list": ("game_list",),
    "game show": ("game_get", "game_observation_get"),
    "game action": ("game_action_submit",),
    "game advance": ("game_advance", "operation_get"),
    "game play": ("game_create", "game_get", "game_timeline_get", "game_advance"),
    "records timeline": ("game_timeline_get",),
    "records replay": ("game_timeline_get",),
    "admin reveal": ("admin_game_reveal",),
    "admin replay-verify": ("admin_replay_verify",),
    "admin operation": ("admin_operation_get",),
    "admin llm-traces": ("admin_llm_traces_get",),
    "admin llm-usage": ("admin_llm_usage_get",),
}

STREAMLIT_WORKSPACE_FEATURES: dict[str, tuple[str, ...]] = {
    "shell": ("runtime_config_get", "runtime_status_get", "session_get"),
    "play": (
        "game_create",
        "game_get",
        "game_observation_get",
        "game_action_submit",
        "game_advance",
        "operation_get",
    ),
    "observe": ("game_list", "game_get", "game_timeline_get"),
    "records": ("game_list", "game_get", "game_timeline_get"),
    "admin": (
        "admin_game_reveal",
        "admin_replay_verify",
        "admin_operation_get",
        "admin_llm_traces_get",
        "admin_llm_usage_get",
    ),
    "preferences": (),
}

__all__ = ["CLI_COMMAND_FEATURES", "STREAMLIT_WORKSPACE_FEATURES"]
