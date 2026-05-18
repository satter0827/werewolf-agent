import typer
from typer.testing import CliRunner

from werewolf_agent.config import get_settings
from werewolf_agent.errors import AppError, ErrorCode
from werewolf_agent.interfaces.cli import app, run_app_command


def test_doctor_command_succeeds() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Werewolf Agent Doctor" in result.output
    assert "dummy" in result.output


def test_run_app_command_handles_app_error_safely() -> None:
    test_app = typer.Typer()

    def fail() -> None:
        raise AppError(
            "The selected action is not allowed.",
            code=ErrorCode.GAME_INVALID_ACTION,
            context={"api_key": "secret"},
        )

    @test_app.command()
    def broken() -> None:
        run_app_command(fail)

    @test_app.command()
    def ok() -> None:
        pass

    result = CliRunner().invoke(test_app, ["broken"])

    assert result.exit_code == 1
    assert "The selected action is not allowed." in result.output
    assert "secret" not in result.output


def test_doctor_command_reports_invalid_configuration_safely() -> None:
    get_settings.cache_clear()
    try:
        result = CliRunner().invoke(app, ["doctor"], env={"WEREWOLF_LOG_LEVEL": "VERBOSE"})
    finally:
        get_settings.cache_clear()

    assert result.exit_code == 1
    assert "Invalid configuration for WEREWOLF_LOG_LEVEL" in result.output
    assert "log_level must be one of" in result.output
