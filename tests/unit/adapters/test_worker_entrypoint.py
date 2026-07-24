import logging

from typer.testing import CliRunner

from werewolf_agent.configuration import AppSettings
from werewolf_agent.interfaces.worker import app as worker_app


def test_worker_once_requires_db_dsn_before_polling_queue(monkeypatch) -> None:
    def fail_process(_settings: object) -> int:
        raise AssertionError("worker should not poll without WEREWOLF_SUPABASE_DB_DSN")

    monkeypatch.setenv("WEREWOLF_LOG_OUTPUT", "none")
    monkeypatch.setattr(worker_app, "get_settings", lambda: AppSettings(_env_file=None))
    monkeypatch.setattr(worker_app, "process_worker_batch", fail_process)

    result = CliRunner().invoke(worker_app.app, ["once"])

    assert result.exit_code == 1
    assert "WEREWOLF_SUPABASE_DB_DSN" in result.output


def test_worker_once_logs_startup_before_polling_queue(monkeypatch, caplog) -> None:
    settings = AppSettings(
        _env_file=None,
        supabase_db_dsn="postgresql://postgres:secret@127.0.0.1:54322/postgres",
    )

    monkeypatch.setattr(worker_app, "get_settings", lambda: settings)
    monkeypatch.setattr(worker_app, "configure_entrypoint_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker_app, "process_worker_batch", lambda _settings: 0)

    with caplog.at_level(logging.INFO, logger=worker_app.__name__):
        result = CliRunner().invoke(worker_app.app, ["once"])

    assert result.exit_code == 0
    records = [
        record for record in caplog.records if record.event_action == "worker.application.started"
    ]
    assert len(records) == 1
    assert records[0].event_outcome == "success"
    assert records[0].worker_mode == "once"
    assert records[0].worker_id == settings.supabase_worker_id
