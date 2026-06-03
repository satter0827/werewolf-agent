"""Typer entry point for the Supabase worker."""

from __future__ import annotations

import typer

from werewolf_agent.interface.runtime import configure_interface_logging, get_settings
from werewolf_agent.interface.worker.service import process_worker_batch, run_worker_forever

app = typer.Typer(no_args_is_help=True, help="Run Supabase request queue workers.")


@app.command()
def once() -> None:
    """Process one configured worker batch and exit."""
    settings = get_settings()
    configure_interface_logging(settings, service_name="werewolf-agent-worker")
    processed = process_worker_batch(settings)
    typer.echo(f"processed={processed}")


@app.command()
def run() -> None:
    """Run the worker loop until interrupted."""
    settings = get_settings()
    configure_interface_logging(settings, service_name="werewolf-agent-worker")
    run_worker_forever(settings)


if __name__ == "__main__":
    app()
