"""HTTP adapters shared by CLI and Streamlit."""

from werewolf_agent.adapters.http.admin_client import HttpAdminClient
from werewolf_agent.adapters.http.game_client import HttpGameClient
from werewolf_agent.adapters.http.public_client import HttpPublicClient

__all__ = ["HttpAdminClient", "HttpGameClient", "HttpPublicClient"]
