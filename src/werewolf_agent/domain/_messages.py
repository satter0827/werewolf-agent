"""Private, stable game-rule messages."""

MESSAGE_CANNOT_INSPECT_UNASSIGNED_ROLE = "Cannot inspect a player without an assigned role."
MESSAGE_EXPECTED_NIGHT_ACTION = "Expected a night action."
MESSAGE_EXPECTED_SPEECH_ACTION = "Expected a speech action."
MESSAGE_EXPECTED_VOTE_ACTION = "Expected a vote action."
MESSAGE_EXPLICIT_ROLES_MUST_MATCH_ROLE_COUNTS = "Explicit roles must match role counts."
MESSAGE_PASS_ACTION_FORBIDS_PAYLOAD = "A pass action cannot include a target or message."
MESSAGE_PLAYER_COUNT_AT_LEAST_ONE = "Player count must be at least one."
MESSAGE_PLAYER_IDS_MUST_BE_UNIQUE = "Player ids must be unique."
MESSAGE_PLAYER_LIST_LENGTH_MUST_MATCH_CONFIG = "Player list length must match player count."
MESSAGE_PLAYER_ROLES_ALL_OR_NONE = "Player roles must be assigned to all players or none."
MESSAGE_ROLE_ABILITIES_MUST_BE_UNIQUE = "Role abilities must be unique."
MESSAGE_ROLE_COUNTS_MUST_SUM_TO_PLAYER_COUNT = "Role counts must sum to player count."
MESSAGE_ROLE_COUNTS_REQUIRE_VILLAGE_SIDE = "Role counts require a village faction."
MESSAGE_ROLE_COUNTS_REQUIRE_WEREWOLF = "Role counts require a werewolf faction."
MESSAGE_ROLES_REQUIRED = "At least one role is required."
MESSAGE_SELF_VOTING_DISABLED = "Self voting is disabled."
MESSAGE_SPEECH_ACTION_FORBIDS_TARGET = "A speech action cannot include a target."
MESSAGE_SPEECH_ACTION_REQUIRES_MESSAGE = "A speech action requires a message."
MESSAGE_UNSUPPORTED_AGENT_ACTION = "Unsupported game action."
MESSAGE_UNSUPPORTED_NIGHT_ACTION = "Unsupported night action."


def message_action_not_available(action_type: str, phase: str) -> str:
    return f"Action {action_type} is not available during {phase}."


def message_cannot_advance_phase(phase: str) -> str:
    return f"Cannot advance phase: {phase}."


def message_expected_phase(expected: str, actual: str) -> str:
    return f"Expected phase {expected}, got {actual}."


def message_message_not_allowed(action_type: str, subject: str) -> str:
    return f"{action_type} {subject} cannot include a message."


def message_player_not_alive(player_id: str) -> str:
    return f"Player is not alive: {player_id}."


def message_role_count_must_be_zero_or_greater(role_id: str) -> str:
    return f"Role count must be zero or greater: {role_id}."


def message_target_required(action_type: str, subject: str) -> str:
    return f"{action_type} {subject} requires a target."


def message_unknown_player_id(player_id: str) -> str:
    return f"Unknown player id: {player_id}."


def message_unknown_role_in_role_counts(role_id: str) -> str:
    return f"Unknown role in role counts: {role_id}."


def message_unsupported_abilities(abilities: list[str]) -> str:
    return f"Unsupported abilities: {', '.join(abilities)}."


def message_unsupported_faction(faction: str) -> str:
    return f"Unsupported faction: {faction}."


def message_unsupported_type(value: str, subject: str) -> str:
    return f"Unsupported {subject} type: {value}."
