"""Serialization boundary between immutable domain values and persistence data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any, cast

from werewolf_agent.domain.state import (
    AbilityDefinition,
    Action,
    ActionType,
    GameConfig,
    GameHistory,
    GameSetup,
    GameState,
    InspectionResult,
    LocalRules,
    NightResult,
    PendingActions,
    Phase,
    Player,
    PlayerStatus,
    RoleCatalog,
    RoleDefinition,
    SpeechRecord,
    VoteResult,
    WinResult,
)


def domain_to_data(value: Any) -> Any:
    """Convert a domain value to JSON-compatible Python data."""
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: domain_to_data(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {
            str(key.value if isinstance(key, Enum) else key): domain_to_data(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [domain_to_data(item) for item in value]
    return value


def game_setup_from_data(data: Mapping[str, Any]) -> GameSetup:
    """Build validated setup values from an application payload."""
    return GameSetup(players=tuple(_player(item) for item in _sequence(data.get("players"))))


def action_from_data(data: Mapping[str, Any]) -> Action:
    """Build one validated domain action from an application payload."""
    return Action(
        type=ActionType(str(data["type"])),
        player_id=str(data["player_id"]),
        reason=str(data.get("reason") or ""),
        target_id=_optional_text(data.get("target_id")),
        message=_optional_text(data.get("message")),
    )


def game_state_from_data(data: Mapping[str, Any]) -> GameState:
    """Build a validated immutable aggregate snapshot from persistence data."""
    config = _mapping(data["config"])
    players = _mapping(data["players"])
    return GameState(
        config=game_config_from_data(config),
        phase=Phase(str(data["phase"])),
        day=int(data["day"]),
        players={str(key): _player(value) for key, value in players.items()},
        history=_history(_mapping(data.get("history", {}))),
        pending_actions=_pending(_mapping(data.get("pending_actions", {}))),
        ability_uses={
            str(player_id): {
                str(ability_id): int(count) for ability_id, count in _mapping(uses).items()
            }
            for player_id, uses in _mapping(data.get("ability_uses", {})).items()
        },
        win_result=_win(data.get("win_result")),
    )


def game_config_from_data(data: Mapping[str, Any]) -> GameConfig:
    """Build validated domain configuration from persistence data."""
    roles_data = _mapping(_mapping(data["roles"])["roles"])
    abilities_data = _mapping(data["abilities"])
    return GameConfig(
        player_count=int(data["player_count"]),
        role_counts={str(key): int(value) for key, value in _mapping(data["role_counts"]).items()},
        rules=LocalRules(**dict(_mapping(data["rules"]))),
        roles=RoleCatalog(
            roles={
                str(key): RoleDefinition(
                    identity_faction=str(_mapping(value)["identity_faction"]),
                    victory_team=str(_mapping(value)["victory_team"]),
                    abilities=tuple(
                        str(item) for item in _sequence(_mapping(value).get("abilities"))
                    ),
                )
                for key, value in roles_data.items()
            }
        ),
        abilities={
            str(key): AbilityDefinition(
                phase=Phase(str(_mapping(value)["phase"])),
                action=ActionType(str(_mapping(value)["action"])),
                validation_policy=str(_mapping(value)["validation_policy"]),
                resolution_policy=str(_mapping(value)["resolution_policy"]),
                target_policy=str(_mapping(value)["target_policy"]),
                start_day=int(_mapping(value)["start_day"]),
                effect=str(_mapping(value)["effect"]),
                max_uses=_optional_int(_mapping(value).get("max_uses")),
                result_visibility=str(_mapping(value).get("result_visibility") or "private"),
                resolution_priority=int(_mapping(value).get("resolution_priority") or 100),
            )
            for key, value in abilities_data.items()
        },
        phase_order=tuple(Phase(str(value)) for value in _sequence(data.get("phase_order"))),
    )


def _player(value: Any) -> Player:
    data = _mapping(value)
    return Player(
        id=str(data["id"]),
        name=str(data["name"]),
        role=_optional_text(data.get("role")),
        status=PlayerStatus(str(data.get("status", PlayerStatus.ALIVE.value))),
        eliminated_day=_optional_int(data.get("eliminated_day")),
        killed_night=_optional_int(data.get("killed_night")),
    )


def _history(data: Mapping[str, Any]) -> GameHistory:
    return GameHistory(
        speeches=tuple(
            SpeechRecord(
                day=int(item["day"]),
                player_id=str(item["player_id"]),
                message=str(item["message"]),
                reason=str(item.get("reason") or ""),
            )
            for item in map(_mapping, _sequence(data.get("speeches")))
        ),
        votes=tuple(_vote(item) for item in map(_mapping, _sequence(data.get("votes")))),
        nights=tuple(_night(item) for item in map(_mapping, _sequence(data.get("nights")))),
    )


def _vote(data: Mapping[str, Any]) -> VoteResult:
    return VoteResult(
        day=int(data["day"]),
        tie_break_policy=str(data["tie_break_policy"]),
        votes={str(key): str(value) for key, value in _mapping(data.get("votes", {})).items()},
        counts={str(key): int(value) for key, value in _mapping(data.get("counts", {})).items()},
        tied_player_ids=tuple(str(value) for value in _sequence(data.get("tied_player_ids"))),
        missing_voter_ids=tuple(str(value) for value in _sequence(data.get("missing_voter_ids"))),
        eliminated_player_id=_optional_text(data.get("eliminated_player_id")),
        round=int(data.get("round") or 1),
        requires_revote=bool(data.get("requires_revote", False)),
    )


def _night(data: Mapping[str, Any]) -> NightResult:
    return NightResult(
        day=int(data["day"]),
        attacked_player_id=_optional_text(data.get("attacked_player_id")),
        protected_player_id=_optional_text(data.get("protected_player_id")),
        killed_player_id=_optional_text(data.get("killed_player_id")),
        killed_player_ids=tuple(str(value) for value in _sequence(data.get("killed_player_ids"))),
        inspections=tuple(
            InspectionResult(
                day=int(item["day"]),
                seer_id=str(item["seer_id"]),
                target_id=str(item["target_id"]),
                target_role=str(item["target_role"]),
                target_faction=str(item["target_faction"]),
            )
            for item in map(_mapping, _sequence(data.get("inspections")))
        ),
    )


def _pending(data: Mapping[str, Any]) -> PendingActions:
    return PendingActions(
        votes={
            str(key): action_from_data(_mapping(value))
            for key, value in _mapping(data.get("votes", {})).items()
        },
        night_actions={
            str(key): action_from_data(_mapping(value))
            for key, value in _mapping(data.get("night_actions", {})).items()
        },
        vote_round=int(data.get("vote_round") or 1),
        revote_candidates=tuple(str(value) for value in _sequence(data.get("revote_candidates"))),
    )


def _win(value: Any) -> WinResult | None:
    if value is None:
        return None
    data = _mapping(value)
    return WinResult(
        winner=str(data["winner"]),
        reason=str(data["reason"]),
        day=int(data["day"]),
        winning_player_ids=tuple(str(item) for item in _sequence(data["winning_player_ids"])),
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("domain payload must be an object")
    return cast(Mapping[str, Any], value)


def _sequence(value: Any) -> Sequence[Any]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("domain payload must be an array")
    return cast(Sequence[Any], value)


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


__all__ = [
    "action_from_data",
    "domain_to_data",
    "game_config_from_data",
    "game_setup_from_data",
    "game_state_from_data",
]
