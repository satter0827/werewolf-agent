"""API process entrypoint."""

from __future__ import annotations

import uvicorn

from werewolf_agent.api.bootstrap import create_app
from werewolf_agent.observability import configure_entrypoint_logging
from werewolf_agent.settings import get_settings

app = create_app()


def run() -> None:
    """Run the configured API server."""
    settings = configure_entrypoint_logging(
        get_settings(),
        default_log_file_name="api.jsonl",
        service_name="werewolf-agent-api",
    )
    uvicorn.run(
        "werewolf_agent.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    run()
