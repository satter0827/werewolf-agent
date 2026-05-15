from typer.testing import CliRunner

from werewolf_agent.interfaces.cli import app


def test_doctor_command_succeeds() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Werewolf Agent Doctor" in result.output
    assert "dummy" in result.output
