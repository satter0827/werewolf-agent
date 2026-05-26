#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys
from pathlib import Path


def main():
    """Run administrative tasks."""
    src_path = Path(__file__).resolve().parent / "src"
    sys.path.insert(0, str(src_path))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "werewolf_agent.interfaces.api.config.settings")

    from werewolf_agent.interfaces.api.manage import main as manage_main

    manage_main()


if __name__ == "__main__":
    main()
