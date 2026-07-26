"""Application resultを独立したwire contractへ明示的に投影する."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from werewolf_agent.contracts.schemas import PublicTheme

TWire = TypeVar("TWire", bound=BaseModel)


def wire_model(model_type: type[TWire], source: BaseModel) -> TWire:
    """公開fieldだけを残し、対象wire modelで検証する."""
    source_payload = source.model_dump(mode="json")
    payload = {
        name: source_payload[name] for name in model_type.model_fields if name in source_payload
    }
    state = payload.get("state")
    if isinstance(state, dict):
        state["theme"] = public_theme_payload(state.get("theme"))
    games = payload.get("games")
    if isinstance(games, list):
        for game in games:
            if isinstance(game, dict):
                game["theme"] = public_theme_payload(game.get("theme"))
    if "theme" in payload and "theme" in model_type.model_fields:
        payload["theme"] = public_theme_payload(payload.get("theme"))
    return model_type.model_validate(payload)


def public_theme_payload(value: object) -> object:
    """内部演出定義から公開theme contractのfieldだけを返す."""
    if not isinstance(value, dict):
        return value
    return {name: value[name] for name in PublicTheme.model_fields if name in value}


__all__ = ["public_theme_payload", "wire_model"]
