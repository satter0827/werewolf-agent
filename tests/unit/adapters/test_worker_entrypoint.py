import logging
import traceback

from typer.testing import CliRunner

from werewolf_agent.application.errors import InternalError
from werewolf_agent.settings import AppSettings
from werewolf_agent.worker import app as worker_app

TEST_DATABASE_DSN = (
    "postgresql://postgres:secret@127.0.0.1:54322/postgres"  # pragma: allowlist secret
)


def test_worker_once_requires_db_dsn_before_polling_queue(monkeypatch, caplog) -> None:
    def fail_process(_settings: object, **_kwargs: object) -> int:
        raise AssertionError("worker should not poll without WEREWOLF_SUPABASE_DB_DSN")

    monkeypatch.setenv("WEREWOLF_LOG_OUTPUT", "none")
    monkeypatch.setattr(
        worker_app,
        "configure_entrypoint_logging",
        lambda *args, **kwargs: AppSettings(_env_file=None),
    )
    monkeypatch.setattr(worker_app, "process_worker_batch", fail_process)

    with caplog.at_level(logging.INFO, logger=worker_app.__name__):
        result = CliRunner().invoke(worker_app.app, ["once"])

    assert result.exit_code == 1
    assert "WEREWOLF_SUPABASE_DB_DSN" in result.output
    records = [
        record
        for record in caplog.records
        if record.event_action == "worker.application_error.handled"
    ]
    assert len(records) == 1
    assert records[0].exc_info is None


def test_worker_internal_error_keeps_the_original_cause(monkeypatch, caplog) -> None:
    """安全化した内部障害の原因をworkerのERROR logへ保持する。"""
    settings = AppSettings(
        _env_file=None,
        supabase_db_dsn=TEST_DATABASE_DSN,
    )

    def fail_process(_settings: object, **_kwargs: object) -> int:
        try:
            raise RuntimeError("private worker detail")
        except RuntimeError as cause:
            raise InternalError() from cause

    monkeypatch.setattr(
        worker_app,
        "configure_entrypoint_logging",
        lambda *args, **kwargs: settings,
    )
    monkeypatch.setattr(worker_app, "process_worker_batch", fail_process)

    with caplog.at_level(logging.ERROR, logger=worker_app.__name__):
        result = CliRunner().invoke(worker_app.app, ["once"])

    assert result.exit_code == 1
    record = next(
        record
        for record in caplog.records
        if record.event_action == "worker.application_error.handled"
    )
    assert record.exc_info is not None
    formatted = "".join(traceback.format_exception(*record.exc_info))
    assert "RuntimeError: private worker detail" in formatted
    assert "InternalError" in formatted


def test_worker_once_logs_startup_before_polling_queue(monkeypatch, caplog) -> None:
    settings = AppSettings(
        _env_file=None,
        supabase_db_dsn=TEST_DATABASE_DSN,
    )

    monkeypatch.setattr(
        worker_app,
        "configure_entrypoint_logging",
        lambda *args, **kwargs: settings,
    )
    monkeypatch.setattr(
        worker_app,
        "process_worker_batch",
        lambda _settings, **_kwargs: 0,
    )

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
