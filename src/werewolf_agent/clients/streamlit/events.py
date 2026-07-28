"""Streamlit clientが記録するlog event名."""

from typing import Final

LOG_STREAMLIT_ACTION_SUBMITTED: Final = "streamlit.action.submitted"
LOG_STREAMLIT_ADVANCE_STEP_COMPLETED: Final = "streamlit.advance_step.completed"
LOG_STREAMLIT_ADVANCE_STEP_STARTED: Final = "streamlit.advance_step.started"
LOG_STREAMLIT_APPLICATION_ERROR_HANDLED: Final = "streamlit.application_error.handled"
LOG_STREAMLIT_APPLICATION_STARTED: Final = "streamlit.application.started"
LOG_STREAMLIT_APPLICATION_STOPPED: Final = "streamlit.application.stopped"
LOG_STREAMLIT_GAME_CREATE_FAILED: Final = "streamlit.game.create_failed"
LOG_STREAMLIT_GAME_CREATED: Final = "streamlit.game.created"
LOG_STREAMLIT_REFRESHED: Final = "streamlit.screen.loaded"
LOG_STREAMLIT_RERUN_STARTED: Final = "streamlit.rerun.started"

__all__ = [
    "LOG_STREAMLIT_ACTION_SUBMITTED",
    "LOG_STREAMLIT_ADVANCE_STEP_COMPLETED",
    "LOG_STREAMLIT_ADVANCE_STEP_STARTED",
    "LOG_STREAMLIT_APPLICATION_ERROR_HANDLED",
    "LOG_STREAMLIT_APPLICATION_STARTED",
    "LOG_STREAMLIT_APPLICATION_STOPPED",
    "LOG_STREAMLIT_GAME_CREATED",
    "LOG_STREAMLIT_GAME_CREATE_FAILED",
    "LOG_STREAMLIT_REFRESHED",
    "LOG_STREAMLIT_RERUN_STARTED",
]
