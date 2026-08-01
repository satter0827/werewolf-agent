from typer.testing import CliRunner

from werewolf_agent.clients.cli.app import app
from werewolf_agent.clients.presentation import CLI_COMMAND_FEATURES


def test_cli_uses_complete_setup_commands_without_legacy_create_arguments() -> None:
    assert "setup validate" in CLI_COMMAND_FEATURES
    assert "game create" in CLI_COMMAND_FEATURES
    assert all("custom role" not in command for command in CLI_COMMAND_FEATURES)


def test_cli_exposes_session_and_mfa_commands() -> None:
    runner = CliRunner()

    auth_help = runner.invoke(app, ["auth", "--help"])

    assert auth_help.exit_code == 0
    assert "sign-in" in auth_help.stdout
    assert "mfa-enroll" in auth_help.stdout
    assert "sign-out" in auth_help.stdout
