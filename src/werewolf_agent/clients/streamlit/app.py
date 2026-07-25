"""Streamlit process entrypoint."""

from werewolf_agent.clients.streamlit.views.runtime import main

__all__ = ["main"]


if __name__ == "__main__":
    main()
