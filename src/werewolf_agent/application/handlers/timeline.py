"""Stateless handlers connecting user requirements to the domain."""

from __future__ import annotations

from werewolf_agent.application.handlers.common import (
    _page_limit,
    _parse_game_id,
)
from werewolf_agent.application.models import (
    ApplicationContext,
    GameTimelineResult,
    ListTimelineQuery,
)
from werewolf_agent.application.projections import (
    public_turn_payload_from_record,
)
from werewolf_agent.contracts import (
    GameNotFoundError,
)


def list_timeline(
    query: ListTimelineQuery,
    *,
    dependencies: ApplicationContext,
) -> GameTimelineResult:
    """List public timeline records after a sequence number."""
    game_id = _parse_game_id(query.game_id)
    run = dependencies.repository.get(game_id)
    if run is None:
        raise GameNotFoundError(str(game_id))

    limit = _page_limit(
        query.limit,
        default=dependencies.config.timeline_default_limit,
        maximum=dependencies.config.timeline_max_limit,
        field_name="limit",
    )
    records = dependencies.repository.list_public_turns(
        run.id,
        after=query.after,
        limit=limit,
    )
    next_after = records[-1].sequence if records else query.after
    return GameTimelineResult(
        game_id=str(run.id),
        items=[public_turn_payload_from_record(record) for record in records],
        next_after=next_after,
    )
