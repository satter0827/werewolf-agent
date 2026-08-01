from typer.testing import CliRunner

from werewolf_agent.clients.cli.app import app
from werewolf_agent.clients.cli.commands.common import _vote_evidence_ids
from werewolf_agent.clients.presentation import CLI_COMMAND_FEATURES
from werewolf_agent.contracts.schemas import AvailableActionDescriptor


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


def test_cli_vote_uses_only_server_authorized_evidence_for_the_target() -> None:
    action = AvailableActionDescriptor.model_validate(
        {
            "key": "vote",
            "type": "vote",
            "legal_target_ids": ["p2"],
            "evidence_options": [
                {
                    "evidence_id": "speech-p2",
                    "kind": "discussion",
                    "actor_id": "p2",
                    "topic_id": "p3",
                    "position": "support",
                },
                {
                    "evidence_id": "speech-p3",
                    "kind": "discussion",
                    "actor_id": "p3",
                    "topic_id": "p2",
                    "position": "oppose",
                },
                {
                    "evidence_id": "speech-other",
                    "kind": "discussion",
                    "actor_id": "p3",
                    "topic_id": "p4",
                    "position": "undecided",
                },
            ],
        }
    )

    assert _vote_evidence_ids(action, "p2") == ["speech-p2", "speech-p3"]
