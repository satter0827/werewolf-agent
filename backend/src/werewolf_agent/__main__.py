"""Module execution entry point for ``python -m werewolf_agent``."""

from werewolf_agent.interface.cui.app import app


def main() -> None:
    """Run the command line interface."""
    app()


if __name__ == "__main__":
    main()
