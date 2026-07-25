"""Worker composition root."""

from werewolf_agent.configuration import AppSettings, get_settings
from werewolf_agent.interfaces.worker.service import process_worker_batch, run_worker_forever


def run_once(settings: AppSettings | None = None) -> int:
    """Build worker dependencies and process one batch."""
    return process_worker_batch(settings or get_settings())


def run_forever(settings: AppSettings | None = None) -> None:
    """Build worker dependencies and process operations until interrupted."""
    run_worker_forever(settings or get_settings())
