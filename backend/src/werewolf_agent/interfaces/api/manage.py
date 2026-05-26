"""Django management entry point for installed distributions."""

from __future__ import annotations

import os
import sys


def main() -> None:
    """Run Django administrative commands for the packaged API."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "werewolf_agent.interfaces.api.config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Install the API extra with "
            "`werewolf-agent[api]` before running Django management commands."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
