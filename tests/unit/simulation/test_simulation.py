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
    DecisionTrace,
    FaultAgentFactory,
    RandomLegalAgentFactory,
)
from werewolf_agent.domain import (
    Action,
    CompiledRuleSet,
    Game,
    GameSetup,
    GameView,
    Player,
    build_game_rules,
)
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


class _LongSpeechFactory:
    def __init__(self) -> None:
        self._inner = RandomLegalAgentFactory()

    @property
    def spec(self) -> AgentSpec:
        return self._inner.spec

    def create(self, context: AgentContext) -> AgentSession:
        return _LongSpeechSession(self._inner.create(context))


class _LongSpeechSession:
    def __init__(self, inner: AgentSession) -> None:
        self._inner = inner

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        if any(option.action_type == "speech" for option in request.options):
            return DecisionResponse("speech", message="長すぎる発言です")
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


class _FalseyExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def __bool__(self) -> bool:
        return False

    def decide(
        self,
        session: AgentSession,
        request: DecisionRequest,
        *,
        timeout_seconds: float | None,
    ) -> DecisionResponse:
        _ = timeout_seconds
        self.calls += 1
        return session.decide(request)


class _FalseyTraceSink:
    def __init__(self) -> None:
        self.traces: list[DecisionTrace] = []

    def __bool__(self) -> bool:
        return False

    def record_decision(self, trace: DecisionTrace) -> None:
        self.traces.append(trace)


class _FalseyCancellation(CancellationToken):
    def __bool__(self) -> bool:
        return False


def _rules() -> CompiledRuleSet:
    catalog = build_setup_catalog()
    document = catalog.require_document(catalog.template_order[0])
    mechanics = document.mechanics
    player_count = sum(mechanics.role_counts.values())
    return build_game_rules(
        rule_definition_from_values(
            player_count=player_count,
            role_counts=mechanics.role_counts,
            rules=mechanics.rules.to_mapping(),
            roles={key: value.to_mapping() for key, value in mechanics.roles.items()},
            abilities={key: value.to_mapping() for key, value in mechanics.abilities.items()},
        )
    )


def _game(seed: int = 41) -> Game:
    catalog = build_setup_catalog()
    document = catalog.require_document(catalog.template_order[0])
    player_count = sum(document.mechanics.role_counts.values())
    generated = generate_players(document.player_generation, player_count=player_count, seed=seed)
    return Game.create(
        GameSetup(
            players=tuple(Player(id=item.player_id, name=item.profile.name) for item in generated)
        ),
        rules=_rules(),
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


def test_restore_preserves_execution_position_and_determinism() -> None:
    interrupted_game = _game()
    interrupted_spec = _spec(interrupted_game)
    cancellation = CancellationToken()
    interrupted = SimulationRunner().start(
        interrupted_game,
        interrupted_spec,
        cancellation=cancellation,
    )
    try:
        while interrupted.step().kind is not SimulationStepKind.PHASE_ADVANCED:
            pass
        cancellation.cancel()
        stopped = interrupted.run()
    finally:
        interrupted.close()

    resumed = SimulationRunner().restore(stopped, rules=_rules())
    try:
        resumed_result = resumed.run()
    finally:
        resumed.close()

    reference_game = _game()
    reference = SimulationRunner().run(reference_game, _spec(reference_game))
    resumed_effects = tuple(
        (step.kind, step.events, step.action_type)
        for step in resumed_result.steps
        if step.kind is not SimulationStepKind.CANCELLED
    )
    reference_effects = tuple(
        (step.kind, step.events, step.action_type) for step in reference.steps
    )

    assert resumed_result.stop_reason is SimulationStopReason.FINISHED
    assert resumed_result.state == reference.state
    assert resumed_result.action_count == reference.action_count
    assert resumed_result.phase_count == reference.phase_count
    assert resumed_effects == reference_effects


def test_restore_uses_the_spec_recorded_in_the_result() -> None:
    game = _game()
    spec = _spec(game)
    cancellation = CancellationToken()
    cancellation.cancel()
    session = SimulationRunner().start(game, spec, cancellation=cancellation)
    try:
        result = session.run()
    finally:
        session.close()

    restored = SimulationRunner().restore(result, rules=_rules())
    try:
        assert restored.spec is spec
    finally:
        restored.close()


def test_simulation_honors_falsey_injected_runtime_dependencies() -> None:
    game = _game()
    executor = _FalseyExecutor()
    sink = _FalseyTraceSink()
    session = SimulationRunner().start(
        game,
        _spec(game),
        decision_executor=executor,
        trace_sink=sink,
    )
    try:
        step = session.step()
        while step.kind is SimulationStepKind.PHASE_ADVANCED:
            step = session.step()
        assert step.kind is SimulationStepKind.AGENT_ACTION
        assert executor.calls == 1
        assert len(sink.traces) == 1
    finally:
        session.close()

    cancelled = _FalseyCancellation()
    cancelled.cancel()
    cancelled_game = _game()
    cancelled_session = SimulationRunner().start(
        cancelled_game,
        _spec(cancelled_game),
        cancellation=cancelled,
    )
    try:
        assert cancelled_session.step().stop_reason is SimulationStopReason.CANCELLED
    finally:
        cancelled_session.close()


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
        assert step.actor_id is not None
        assert step.decision_trace.fallback_used
        assert step.decision_trace.error_code == "broken"
        assert step.decision_trace.agent_spec == controllers[step.actor_id].fallback_factory.spec
    finally:
        session.close()


def test_too_long_agent_speech_uses_fallback_and_records_stable_error() -> None:
    """DecisionOptionの文字数上限をSimulationの実行境界でも強制する。"""
    game = _game()
    base = _spec(game)
    controllers = {
        player_id: PlayerController(player_id, _LongSpeechFactory())
        for player_id in base.controllers
    }
    session = SimulationRunner().start(
        game,
        SimulationSpec(
            base.simulation_id,
            base.game_id,
            base.seed,
            controllers,
            base.limits,
            speech_message_max_chars=4,
        ),
    )
    try:
        for _ in range(100):
            step = session.step()
            if step.decision_trace is not None and step.decision_trace.error_code:
                break
        else:
            pytest.fail("speech decision was not reached")
        assert step.decision_trace is not None
        assert step.decision_trace.fallback_used
        assert step.decision_trace.error_code == "agent_message_too_long"
        assert step.decision_trace.response is not None
        assert len(step.decision_trace.response.message or "") <= 4
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
    with pytest.raises(ValueError, match="number"):
        SimulationLimits(decision_timeout_seconds=True)
    with pytest.raises(ValueError, match="number"):
        SimulationLimits(decision_timeout_seconds="1")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive and finite"):
        SimulationLimits(decision_timeout_seconds=float("inf"))
    with pytest.raises(TypeError):
        spec.controllers["new"] = PlayerController("new")  # type: ignore[index]
