"""単一ゲームSimulation contractと決定性を検証する."""

from __future__ import annotations

import random

import pytest

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.agents import (
    AgentContext,
    AgentSession,
    AgentSpec,
    AgentWorld,
    DecisionRequest,
    DecisionResponse,
    FaultAgentFactory,
    RandomLegalAgentFactory,
)
from werewolf_agent.domain import Action, Game, GameSetup, GameView, Player, build_game_rules
from werewolf_agent.setup import generate_players, namespace_seed, rule_definition_from_values
from werewolf_agent.simulation import (
    AgentMetadata,
    CancellationToken,
    PlayerController,
    SimulationLimits,
    SimulationRunner,
    SimulationSpec,
    SimulationStepKind,
    SimulationStopReason,
)


class _CapturingFactory:
    def __init__(self) -> None:
        self._inner = RandomLegalAgentFactory()
        self.requests: list[DecisionRequest] = []

    @property
    def spec(self) -> AgentSpec:
        return self._inner.spec

    def create(self, context: AgentContext) -> AgentSession:
        return _CapturingSession(self._inner.create(context), self.requests)


class _CapturingSession:
    def __init__(self, inner: AgentSession, requests: list[DecisionRequest]) -> None:
        self._inner = inner
        self._requests = requests

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        self._requests.append(request)
        return self._inner.decide(request)

    def close(self) -> None:
        self._inner.close()


class _ChangingMetadata:
    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, _observation: GameView) -> AgentMetadata:
        self.calls += 1
        return AgentMetadata(
            world=AgentWorld(
                "test",
                "Test",
                f"call-{self.calls}",
                "0" * 64,
                "1" * 64,
            )
        )


def _game(seed: int = 41) -> Game:
    catalog = build_setup_catalog()
    document = catalog.require_document(catalog.template_order[0])
    mechanics = document.mechanics
    player_count = sum(mechanics.role_counts.values())
    rules = build_game_rules(
        rule_definition_from_values(
            player_count=player_count,
            role_counts=mechanics.role_counts,
            rules=mechanics.rules.to_mapping(),
            roles={key: value.to_mapping() for key, value in mechanics.roles.items()},
            abilities={key: value.to_mapping() for key, value in mechanics.abilities.items()},
        )
    )
    generated = generate_players(document.player_generation, player_count=player_count, seed=seed)
    return Game.create(
        GameSetup(
            players=tuple(Player(id=item.player_id, name=item.profile.name) for item in generated)
        ),
        rules=rules,
        random=random.Random(namespace_seed(seed, "role_assignment")),
    )


def _spec(game: Game, *, manual_player_id: str | None = None) -> SimulationSpec:
    return SimulationSpec(
        simulation_id="simulation-1",
        game_id="game-1",
        seed=97,
        controllers={
            player_id: PlayerController(
                player_id,
                None if player_id == manual_player_id else RandomLegalAgentFactory(),
            )
            for player_id in game.snapshot().players
        },
        limits=SimulationLimits(max_actions=500, max_phases=50),
    )


def test_same_seed_produces_same_steps_and_state() -> None:
    first_game = _game()
    second_game = _game()

    first = SimulationRunner().run(first_game, _spec(first_game))
    second = SimulationRunner().run(second_game, _spec(second_game))

    assert first.stop_reason is SimulationStopReason.FINISHED
    assert first.state == second.state
    assert tuple((step.kind, step.events) for step in first.steps) == tuple(
        (step.kind, step.events) for step in second.steps
    )
    assert tuple(
        None if step.decision_trace is None else step.decision_trace.response
        for step in first.steps
    ) == tuple(
        None if step.decision_trace is None else step.decision_trace.response
        for step in second.steps
    )


def test_manual_player_waits_without_blocking_available_agent_action() -> None:
    game = _game()
    manual_id = next(iter(game.snapshot().players))
    session = SimulationRunner().start(game, _spec(game, manual_player_id=manual_id))
    try:
        result = session.run()
        assert result.stop_reason is SimulationStopReason.WAITING_FOR_MANUAL

        view = game.view_for(manual_id)
        available = view.available_actions[0]
        targets = view.legal_targets.get(available.key, ())
        action = Action(
            type=available.type,
            player_id=manual_id,
            ability_id=available.ability_id,
            target_id=targets[0] if targets else None,
            message="状況を確認します。" if available.type.value == "speech" else None,
        )
        step = session.submit_manual(action)
        assert step.kind is SimulationStepKind.MANUAL_ACTION
        assert session.run().stop_reason in {
            SimulationStopReason.WAITING_FOR_MANUAL,
            SimulationStopReason.FINISHED,
        }
    finally:
        session.close()


def test_agent_failure_uses_fallback_and_records_stable_error() -> None:
    game = _game()
    spec = _spec(game)
    controllers = {
        player_id: PlayerController(player_id, FaultAgentFactory("broken"))
        for player_id in spec.controllers
    }
    session = SimulationRunner().start(
        game,
        SimulationSpec(spec.simulation_id, spec.game_id, spec.seed, controllers, spec.limits),
    )
    try:
        step = session.step()
        while step.kind is SimulationStepKind.PHASE_ADVANCED:
            step = session.step()
        assert step.decision_trace is not None
        assert step.decision_trace.fallback_used
        assert step.decision_trace.error_code == "broken"
    finally:
        session.close()


def test_limits_and_cancellation_are_explicit_stop_reasons() -> None:
    limited_game = _game()
    base = _spec(limited_game)
    limited = SimulationSpec(
        base.simulation_id,
        base.game_id,
        base.seed,
        base.controllers,
        SimulationLimits(max_actions=1, max_phases=50),
    )
    assert SimulationRunner().run(limited_game, limited).stop_reason is (
        SimulationStopReason.ACTION_LIMIT
    )

    cancelled_game = _game()
    token = CancellationToken()
    token.cancel()
    session = SimulationRunner().start(cancelled_game, _spec(cancelled_game), cancellation=token)
    try:
        assert session.run().stop_reason is SimulationStopReason.CANCELLED
    finally:
        session.close()


def test_action_limit_does_not_block_a_ready_phase_advance() -> None:
    game = _game()
    base = _spec(game)
    session = SimulationRunner().start(
        game,
        SimulationSpec(
            base.simulation_id,
            base.game_id,
            base.seed,
            base.controllers,
            SimulationLimits(
                max_actions=len(game.snapshot().players),
                max_phases=1,
            ),
        ),
    )
    try:
        result = session.run()
    finally:
        session.close()

    assert result.stop_reason is SimulationStopReason.PHASE_LIMIT
    assert result.phase_count == 1
    assert result.action_count <= len(game.snapshot().players)


def test_metadata_provider_is_resolved_for_every_decision() -> None:
    game = _game()
    factory = _CapturingFactory()
    metadata = _ChangingMetadata()
    spec = SimulationSpec(
        "dynamic-metadata",
        "game-1",
        19,
        {
            player_id: PlayerController(
                player_id,
                factory,
                metadata_provider=metadata,
            )
            for player_id in game.snapshot().players
        },
    )
    session = SimulationRunner().start(game, spec)
    try:
        while len(factory.requests) < 3:
            assert session.step().stop_reason is None
    finally:
        session.close()

    assert metadata.calls == len(factory.requests)
    assert [request.observation.world.premise for request in factory.requests] == [
        "call-1",
        "call-2",
        "call-3",
    ]


def test_spec_rejects_controller_mismatch_and_invalid_limits() -> None:
    game = _game()
    spec = _spec(game)
    with pytest.raises(ValueError, match="exactly match"):
        SimulationRunner().start(
            game, SimulationSpec("s", "g", 1, {"other": PlayerController("other")})
        )
    with pytest.raises(ValueError, match="positive"):
        SimulationLimits(max_actions=0)
    with pytest.raises(TypeError):
        spec.controllers["new"] = PlayerController("new")  # type: ignore[index]
