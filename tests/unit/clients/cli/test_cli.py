from werewolf_agent.clients.presentation import CLI_COMMAND_FEATURES


def test_cli_uses_complete_setup_commands_without_legacy_create_arguments() -> None:
    assert "setup validate" in CLI_COMMAND_FEATURES
    assert "game create" in CLI_COMMAND_FEATURES
    assert all("custom role" not in command for command in CLI_COMMAND_FEATURES)
