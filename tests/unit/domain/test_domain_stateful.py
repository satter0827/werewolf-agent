"""Hypothesisが生成・縮小するdomain操作列の状態不変条件。"""

from copy import deepcopy

import pytest
from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from werewolf_agent.domain import RuleViolation
from werewolf_agent.domain.state import Action, ActionType, Phase

from .test_domain_game import start_fixed_run


class GameStateMachine(RuleBasedStateMachine):
    """公開observationだけを使って一phaseずつゲームを進める。"""

    def __init__(self) -> None:
        super().__init__()
        self.run = start_fixed_run(seed=7)
        self.player_ids = tuple(self.run.snapshot.players)

    @rule(data=st.data())
    def submit_legal_actions_and_advance(self, data: st.DataObject) -> None:
        if self.run.snapshot.is_finished:
            before = deepcopy(self.run.snapshot)
            with pytest.raises(RuleViolation):
                self.run.advance()
            assert self.run.snapshot == before
            return

        for player_id in self.player_ids:
            observation = self.run.observe(player_id)
            while observation.available_actions:
                action_type = data.draw(st.sampled_from(observation.available_actions))
                action = self._action(data, player_id, action_type)
                self.run.submit(action)
                observation = self.run.observe(player_id)
        self.run.advance()

    @rule(player_index=st.integers(min_value=0, max_value=4))
    def rejected_action_is_atomic(self, player_index: int) -> None:
        player_id = self.player_ids[player_index]
        before = deepcopy(self.run.snapshot)
        with pytest.raises(RuleViolation):
            self.run.submit(Action.vote(player_id, player_id))
        assert self.run.snapshot == before

    @invariant()
    def observations_do_not_reveal_unknown_roles(self) -> None:
        snapshot = self.run.snapshot
        for player_id in self.player_ids:
            observation = self.run.observe(player_id)
            assert set(observation.legal_targets) <= set(observation.available_actions)
            for player in observation.players:
                if player.role is not None:
                    assert observation.known_roles[player.id] == player.role
                elif not snapshot.is_finished:
                    assert player.id not in observation.known_roles

    @invariant()
    def stable_identity_and_terminal_shape(self) -> None:
        snapshot = self.run.snapshot
        assert tuple(snapshot.players) == self.player_ids
        assert snapshot.day >= 1
        assert (snapshot.phase is Phase.FINISHED) == snapshot.is_finished
        assert (snapshot.win_result is not None) == snapshot.is_finished

    def _action(
        self,
        data: st.DataObject,
        player_id: str,
        action_type: ActionType,
    ) -> Action:
        if action_type is ActionType.SPEECH:
            return Action.speech(player_id, "hypothesis")
        targets = self.run.observe(player_id).legal_targets[action_type]
        target_id = data.draw(st.sampled_from(targets))
        constructors = {
            ActionType.VOTE: Action.vote,
            ActionType.WEREWOLF_ATTACK: Action.attack,
            ActionType.SEER_INSPECT: Action.inspect,
            ActionType.KNIGHT_GUARD: Action.guard,
        }
        return constructors[action_type](player_id, target_id)


TestGameStateMachine = GameStateMachine.TestCase
TestGameStateMachine.settings = settings(
    max_examples=24,
    stateful_step_count=24,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
