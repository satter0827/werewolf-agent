"""Worker公開entrypointの組み立て契約。"""

from typer.testing import CliRunner

from werewolf_agent.worker.app import app


def test_worker_entrypoint_exposes_bounded_run_modes() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "once" in result.stdout
    assert "run" in result.stdout
