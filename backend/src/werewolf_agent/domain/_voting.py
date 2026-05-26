"""Vote recording and resolution."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Mapping

from werewolf_agent.contracts import GameError
from werewolf_agent.domain._rules import alive_players, mark_dead, require_alive, require_phase
from werewolf_agent.domain.models import (
    GameConfig,
    GameSnapshot,
    Phase,
    TieBreakPolicy,
    VoteAction,
    VoteResult,
)


def record_vote(
    snapshot: GameSnapshot,
    config: GameConfig,
    pending_votes: Mapping[str, VoteAction],
    action: VoteAction,
) -> dict[str, VoteAction]:
    """Validate and return pending votes with one vote recorded."""
    require_phase(snapshot, Phase.VOTING)
    require_alive(snapshot, action.player_id)
    require_alive(snapshot, action.target_id)
    if not config.allow_self_vote and action.player_id == action.target_id:
        raise GameError(
            "Self-voting is disabled for this game.",
            context={"player_id": action.player_id, "target_id": action.target_id},
        )

    updated_votes = dict(pending_votes)
    updated_votes[action.player_id] = action
    return updated_votes


def resolve_votes(
    snapshot: GameSnapshot,
    config: GameConfig,
    pending_votes: Mapping[str, VoteAction],
    rng: random.Random,
) -> tuple[GameSnapshot, VoteResult]:
    """Resolve all currently pending votes."""
    require_phase(snapshot, Phase.VOTING)

    vote_targets = {player_id: action.target_id for player_id, action in pending_votes.items()}
    counts = dict(Counter(vote_targets.values()))
    alive_voter_ids = [player.player_id for player in alive_players(snapshot)]
    missing_voter_ids = [
        player_id for player_id in alive_voter_ids if player_id not in pending_votes
    ]

    eliminated_player_id: str | None = None
    tied_player_ids: list[str] = []
    if counts:
        max_votes = max(counts.values())
        tied_player_ids = sorted(
            player_id for player_id, count in counts.items() if count == max_votes
        )
        if len(tied_player_ids) == 1:
            eliminated_player_id = tied_player_ids[0]
        elif config.tie_break_policy is TieBreakPolicy.RANDOM_ELIMINATION:
            eliminated_player_id = rng.choice(tied_player_ids)

    updated_snapshot = snapshot
    if eliminated_player_id is not None:
        updated_snapshot = mark_dead(
            snapshot,
            eliminated_player_id,
            eliminated_day=snapshot.day,
        )

    result = VoteResult(
        day=snapshot.day,
        votes=vote_targets,
        counts=counts,
        tied_player_ids=tied_player_ids,
        missing_voter_ids=missing_voter_ids,
        eliminated_player_id=eliminated_player_id,
        tie_break_policy=config.tie_break_policy,
    )
    updated_history = [*updated_snapshot.vote_history, result]
    return updated_snapshot.model_copy(update={"vote_history": updated_history}), result
