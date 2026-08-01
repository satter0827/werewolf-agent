"""Vote recording and resolution rules."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Mapping
from dataclasses import replace

from werewolf_agent.domain._messages import (
    MESSAGE_EXPECTED_VOTE_ACTION,
    MESSAGE_SELF_VOTING_DISABLED,
)
from werewolf_agent.domain.errors import GameError
from werewolf_agent.domain.rule_packs import AbilityPolicy, VotingPolicy
from werewolf_agent.domain.rules.player_rules import (
    alive_players,
    mark_dead,
    require_alive,
    require_phase,
    resolve_death_reactions,
)
from werewolf_agent.domain.state import (
    Action,
    ActionType,
    GameConfig,
    GameState,
    Phase,
    VoteResolution,
    VoteResult,
)


def record_vote(
    snapshot: GameState,
    config: GameConfig,
    pending_votes: Mapping[str, Action],
    action: Action,
    *,
    candidates: tuple[str, ...] = (),
) -> dict[str, Action]:
    """Validate and return pending votes with one vote recorded."""
    require_phase(snapshot, Phase.VOTING)
    require_alive(snapshot, action.player_id)
    target_id = _vote_target(action)
    if not action.reason or len(action.reason) > config.voting.reason_max_chars:
        raise GameError("Vote requires a public reason within the configured maximum length.")
    require_alive(snapshot, target_id)
    if candidates and target_id not in candidates:
        raise GameError(
            "Vote target is not a revote candidate.",
            context={"target_id": target_id, "candidate_ids": candidates},
        )
    if not config.voting.allow_self_vote and action.player_id == target_id:
        raise GameError(
            MESSAGE_SELF_VOTING_DISABLED,
            context={"player_id": action.player_id, "target_id": target_id},
        )

    updated_votes = dict(pending_votes)
    updated_votes[action.player_id] = action
    return updated_votes


def resolve_votes(
    snapshot: GameState,
    pending_votes: Mapping[str, Action],
    rng: random.Random,
    *,
    vote_round: int = 1,
    ability_policy: AbilityPolicy,
    policy: VotingPolicy,
) -> tuple[GameState, VoteResult]:
    """Policy Outcomeを検証し、死亡と履歴をDomainで一括適用する."""
    require_phase(snapshot, Phase.VOTING)
    random_state = rng.getstate()
    try:
        resolution = policy.resolve(
            snapshot,
            pending_votes,
            rng,
            vote_round=vote_round,
        )
        _validate_outcome(snapshot, pending_votes, resolution, vote_round=vote_round)

        result = VoteResult(**resolution.__dict__)

        updated_snapshot = snapshot
        if result.eliminated_player_id is not None:
            updated_snapshot = mark_dead(
                snapshot,
                result.eliminated_player_id,
                eliminated_day=snapshot.day,
            )
            updated_snapshot, _reaction_deaths = resolve_death_reactions(
                updated_snapshot,
                [result.eliminated_player_id],
                rng,
                policy=ability_policy,
                during_night=False,
            )

        history = replace(
            updated_snapshot.history,
            votes=(*updated_snapshot.history.votes, result),
        )
        return replace(updated_snapshot, history=history), result
    except Exception:
        rng.setstate(random_state)
        raise


class CoreVotingPolicy:
    """組み込みの単純多数、tie、revote規則を実装する."""

    def resolve(
        self,
        state: GameState,
        pending_votes: Mapping[str, Action],
        random: random.Random,
        *,
        vote_round: int,
    ) -> VoteResolution:
        """現在の組み込み投票規則からstate非変更Outcomeを返す."""
        vote_targets = {
            player_id: _vote_target(action) for player_id, action in pending_votes.items()
        }
        vote_reasons = {player_id: action.reason for player_id, action in pending_votes.items()}
        counts = dict(Counter(vote_targets.values()))
        alive_voter_ids = [player.id for player in alive_players(state)]
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
            elif state.config.voting.tie_resolution == "random_elimination":
                eliminated_player_id = random.choice(tied_player_ids)
        requires_revote = bool(
            counts
            and len(tied_player_ids) > 1
            and state.config.voting.tie_resolution == "revote"
            and vote_round == 1
        )
        return VoteResolution(
            day=state.day,
            votes=vote_targets,
            reasons=vote_reasons,
            counts=counts,
            tied_player_ids=tuple(tied_player_ids),
            missing_voter_ids=tuple(missing_voter_ids),
            eliminated_player_id=eliminated_player_id,
            tie_break_policy=state.config.voting.tie_resolution,
            round=vote_round,
            requires_revote=requires_revote,
        )


def _validate_outcome(
    snapshot: GameState,
    pending_votes: Mapping[str, Action],
    result: VoteResolution,
    *,
    vote_round: int,
) -> None:
    alive_ids = {player.id for player in alive_players(snapshot)}
    expected_votes = {
        player_id: _vote_target(action) for player_id, action in pending_votes.items()
    }
    if (
        not isinstance(result.day, int)
        or isinstance(result.day, bool)
        or not isinstance(result.round, int)
        or isinstance(result.round, bool)
        or result.day != snapshot.day
        or result.round != vote_round
    ):
        raise ValueError("voting outcome day and round must match the current vote")
    if dict(result.votes) != expected_votes:
        raise ValueError("voting outcome votes must match pending votes")
    expected_reasons = {player_id: action.reason for player_id, action in pending_votes.items()}
    if dict(result.reasons) != expected_reasons:
        raise ValueError("voting outcome reasons must match pending votes")
    if set(result.counts) - alive_ids or any(
        not isinstance(count, int) or isinstance(count, bool) or count < 0
        for count in result.counts.values()
    ):
        raise ValueError("voting outcome counts must reference alive players")
    if set(result.tied_player_ids) - alive_ids:
        raise ValueError("voting outcome tied players must be alive")
    if len(result.tied_player_ids) != len(set(result.tied_player_ids)):
        raise ValueError("voting outcome tied players must be unique")
    if set(result.missing_voter_ids) - alive_ids:
        raise ValueError("voting outcome missing voters must be alive")
    if len(result.missing_voter_ids) != len(set(result.missing_voter_ids)):
        raise ValueError("voting outcome missing voters must be unique")
    if set(result.missing_voter_ids) != alive_ids - set(pending_votes):
        raise ValueError("voting outcome missing voters must match pending votes")
    if not isinstance(result.tie_break_policy, str) or not result.tie_break_policy.strip():
        raise ValueError("voting outcome tie break policy must not be blank")
    if result.eliminated_player_id is not None and result.eliminated_player_id not in alive_ids:
        raise ValueError("voting outcome eliminated player must be alive")
    if not isinstance(result.requires_revote, bool):
        raise ValueError("voting outcome requires_revote must be a boolean")
    if result.requires_revote and (
        not result.tied_player_ids or result.eliminated_player_id is not None
    ):
        raise ValueError("voting outcome revote requires candidates")


def _vote_target(action: Action) -> str:
    if action.type is not ActionType.VOTE or action.target_id is None:
        raise GameError(MESSAGE_EXPECTED_VOTE_ACTION)
    return action.target_id
