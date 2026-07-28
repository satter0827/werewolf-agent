"""Choice metadata derived independently from runtime default values."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Literal

from werewolf_agent.settings.constants import (
    CLI_OUTPUT_FORMAT_CHOICE_SET,
    LLM_PROVIDER_CHOICE_SET,
    LOG_OUTPUT_CHOICE_SET,
)
from werewolf_agent.settings.loading import load_packaged_defaults

PACKAGED_DEFAULTS: Mapping[str, object] = load_packaged_defaults()
APP_NAME: Final = str(PACKAGED_DEFAULTS["app_name"])

LOG_LEVEL_NAMES: Final = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
LOG_OUTPUT_NAMES: Final = LOG_OUTPUT_CHOICE_SET
CLI_OUTPUT_FORMAT_NAMES: Final = CLI_OUTPUT_FORMAT_CHOICE_SET
STREAMLIT_LANGUAGE_NAMES: Final = frozenset({"ja", "en"})
STREAMLIT_SIDEBAR_STATE_NAMES: Final = frozenset({"auto", "expanded", "collapsed"})
LLM_PROVIDER_NAMES: Final = LLM_PROVIDER_CHOICE_SET

StreamlitLanguage = Literal["ja", "en"]
StreamlitSidebarState = Literal["auto", "expanded", "collapsed"]
