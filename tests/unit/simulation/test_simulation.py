"""単一ゲームSimulation contractと決定性を検証する."""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.agents import (
    AgentContext,
    AgentDecisionError,
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
    DiscussionPosition,
    DiscussionRelation,
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
        option = next(
            (item for item in request.options if item.action_type == "speech"),
            None,
        )
        if option is not None:
            reference_id = option.legal_reference_ids[0] if option.legal_reference_ids else None
            return DecisionResponse(
                "speech",
                utterance="長すぎる発言です",
                topic_id=option.legal_topic_ids[0],
                position="oppose" if reference_id else "support",
                relation="challenge" if reference_id else "independent",
                evidence_id=reference_id,
                response_to_id=reference_id,
            )
        return self._inner.decide(request)

    def close(self) -> None:
        self._inner.close()


class _InvalidRelationFactory:
    def __init__(self) -> None:
        self._inner = RandomLegalAgentFactory()

    @property
    def spec(self) -> AgentSpec:
        return self._inner.spec

    def create(self, context: AgentContext) -> AgentSession:
        return _InvalidRelationSession(self._inner.create(context))


class _InvalidRelationSession:
    def __init__(self, inner: AgentSession) -> None:
        self._inner = inner

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        option = next(
            (
                item
                for item in request.options
                if item.action_type == "speech" and item.legal_reference_ids
            ),
            None,
        )
        if option is None:
            return self._inner.decide(request)
        evidence = next(
            item
            for item in option.evidence_options
            if item.evidence_id == option.legal_reference_ids[0]
        )
        incompatible_position = "oppose" if evidence.position == "support" else "support"
        return DecisionResponse(
            "speech",
            utterance="参照発言とは異なる内容を述べます。",
            topic_id=evidence.topic_id,
            position=incompatible_position,
            relation="support",
            evidence_id=evidence.evidence_id,
            response_to_id=evidence.evidence_id,
        )

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


class _FallbackTimeoutExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def decide(
        self,
        session: AgentSession,
        request: DecisionRequest,
        *,
        timeout_seconds: float | None,
    ) -> DecisionResponse:
        _ = session, request, timeout_seconds
        self.calls += 1
        if self.calls == 1:
            raise AgentDecisionError("primary_failed", {"primary": "detail"})
        raise AgentDecisionError(
            "agent_timeout",
            {"elapsed_seconds": 1.25, "timeout_seconds": 1.0},
        )


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
            discussion=mechanics.discussion.to_mapping(),
            voting=mechanics.voting.to_mapping(),
            night=mechanics.night.to_mapping(),
            lifecycle=mechanics.lifecycle.to_mapping(),
            roles={key: value.to_mapping() for key, value in mechanics.roles.items()},
            abilities={key: value.to_mapping() for key, value in mechanics.abilities.items()},
        )
    )


def _game(seed: int = 41, *, rules: CompiledRuleSet | None = None) -> Game:
    catalog = build_setup_catalog()
    document = catalog.require_document(catalog.template_order[0])
    player_count = sum(document.mechanics.role_counts.values())
    generated = generate_players(document.player_generation, player_count=player_count, seed=seed)
    return Game.create(
        GameSetup(
            players=tuple(Player(id=item.player_id, name=item.profile.name) for item in generated)
        ),
        rules=rules or _rules(),
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
        if available.type.value == "speech":
            round_ = view.discussion_round
            speeches = {speech.speech_id: speech for speech in view.history.speeches}
            reference_id = (
                next(
                    reference_id
                    for reference_id in round_.reference_ids
                    if speeches[reference_id].player_id != manual_id
                )
                if round_ is not None and round_.reference_ids
                else None
            )
            action = Action.speech(
                manual_id,
                "その発言には異論があります。" if reference_id else "状況を確認します。",
                topic_id=(
                    speeches[reference_id].topic_id
                    if reference_id
                    else next(
                        player.id
                        for player in view.players
                        if player.id != manual_id and player.is_alive
                    )
                ),
                position=(
                    DiscussionPosition.OPPOSE if reference_id else DiscussionPosition.SUPPORT
                ),
                relation=(
                    DiscussionRelation.CHALLENGE if reference_id else DiscussionRelation.INDEPENDENT
                ),
                evidence_id=reference_id,
                response_to_id=reference_id,
            )
        elif available.type.value == "vote":
            speech = next(
                (
                    item
                    for item in reversed(view.history.speeches)
                    if targets[0] in {item.player_id, item.topic_id}
                ),
                None,
            )
            if speech is not None:
                evidence_id = speech.speech_id
            else:
                result = next(
                    item
                    for item in reversed(view.history.discussions)
                    if targets[0] in item.passed_player_ids
                )
                evidence_id = f"pass:{result.day}:{result.round_id}:{targets[0]}"
            action = Action.vote(
                manual_id,
                targets[0],
                reason="状況から判断します。",
                evidence_id=evidence_id,
            )
        elif available.type.value == "use_ability":
            action = Action.use_ability(manual_id, available.ability_id or "", targets[0])
        else:
            action = Action.pass_(manual_id)
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
        assert len(step.decision_trace.response.utterance or "") <= 4
    finally:
        session.close()


def test_invalid_response_relation_uses_fallback_before_domain_submit() -> None:
    """relationとpositionの不正な組合せをAgent境界でfallbackへ送る。"""
    game = _game()
    base = _spec(game)
    controllers = {
        player_id: PlayerController(player_id, _InvalidRelationFactory())
        for player_id in base.controllers
    }
    session = SimulationRunner().start(
        game,
        SimulationSpec(base.simulation_id, base.game_id, base.seed, controllers, base.limits),
    )
    try:
        for _ in range(100):
            step = session.step()
            if (
                step.decision_trace is not None
                and step.decision_trace.error_code == "agent_response_support_mismatch"
            ):
                break
        else:
            pytest.fail("response decision was not reached")
        assert step.decision_trace is not None
        assert step.decision_trace.fallback_used
        assert step.kind is SimulationStepKind.AGENT_ACTION
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


def test_expired_full_run_deadline_stops_before_any_action() -> None:
    game = _game()
    base = _spec(game)
    session = SimulationRunner().start(
        game,
        SimulationSpec(
            base.simulation_id,
            base.game_id,
            base.seed,
            base.controllers,
            base.limits,
            deadline_at=datetime.now(UTC) - timedelta(seconds=1),
        ),
    )
    try:
        result = session.run()
    finally:
        session.close()

    assert result.stop_reason is SimulationStopReason.DEADLINE_REACHED
    assert result.steps[-1].kind is SimulationStepKind.DEADLINE_REACHED
    assert result.action_count == 0
    assert result.phase_count == 0


def test_deadline_expiry_after_primary_failure_skips_fallback(monkeypatch) -> None:
    game = _game()
    base = _spec(game)
    fallback = _CapturingFactory()
    controllers = {
        player_id: PlayerController(
            player_id,
            FaultAgentFactory("broken"),
            fallback_factory=fallback,
        )
        for player_id in base.controllers
    }
    monkeypatch.setattr(
        "werewolf_agent.simulation.session._request_deadline_expired",
        lambda _request: True,
    )
    session = SimulationRunner().start(
        game,
        SimulationSpec(base.simulation_id, base.game_id, base.seed, controllers, base.limits),
    )
    try:
        step = session.step()
    finally:
        session.close()

    assert step.stop_reason is SimulationStopReason.DEADLINE_REACHED
    assert fallback.requests == []


def test_fallback_timeout_becomes_deadline_stop_with_trace() -> None:
    game = _game()
    base = _spec(game)
    executor = _FallbackTimeoutExecutor()
    sink = _FalseyTraceSink()
    session = SimulationRunner().start(
        game,
        SimulationSpec(
            base.simulation_id,
            base.game_id,
            base.seed,
            base.controllers,
            SimulationLimits(decision_timeout_seconds=60),
        ),
        decision_executor=executor,
        trace_sink=sink,
    )
    try:
        step = session.step()
        while step.kind is SimulationStepKind.PHASE_ADVANCED:
            step = session.step()
    finally:
        session.close()

    assert step.stop_reason is SimulationStopReason.DEADLINE_REACHED
    assert executor.calls == 2
    assert len(sink.traces) == 1
    assert sink.traces[0].error_code == "agent_timeout"
    assert sink.traces[0].diagnostics == {
        "elapsed_seconds": 1.25,
        "timeout_seconds": 1.0,
        "primary_error_code": "primary_failed",
        "primary_diagnostics": {"primary": "detail"},
    }


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


def test_response_relations_are_derived_from_active_setup() -> None:
    """Agentへ広告するresponse relationをactive setupの許可値へ限定する."""
    rules = _rules()
    opening_stage, response_stage = rules.config.discussion.stages
    rules = replace(
        rules,
        config=replace(
            rules.config,
            discussion=replace(
                rules.config.discussion,
                stages=(
                    opening_stage,
                    replace(
                        response_stage,
                        allowed_relations=(DiscussionRelation.SUPPORT,),
                    ),
                ),
            ),
        ),
    )
    game = _game(rules=rules)
    factory = _CapturingFactory()
    base = _spec(game)
    controllers = {
        player_id: PlayerController(player_id, factory) for player_id in base.controllers
    }
    session = SimulationRunner().start(
        game,
        SimulationSpec(base.simulation_id, base.game_id, base.seed, controllers, base.limits),
    )
    try:
        for _ in range(100):
            session.step()
            response_request = next(
                (
                    request
                    for request in factory.requests
                    if request.observation.procedure is not None
                    and request.observation.procedure.stage_id == "response"
                ),
                None,
            )
            if response_request is not None:
                break
        else:
            pytest.fail("response decision was not reached")
    finally:
        session.close()

    assert response_request is not None
    speech = next(item for item in response_request.options if item.action_type == "speech")
    assert speech.legal_relations == ("support",)


def test_per_call_timeout_is_propagated_as_request_deadline() -> None:
    game = _game()
    factory = _CapturingFactory()
    started_at = datetime.now(UTC)
    spec = SimulationSpec(
        "call-deadline",
        "game-1",
        19,
        {player_id: PlayerController(player_id, factory) for player_id in game.snapshot().players},
        limits=SimulationLimits(decision_timeout_seconds=2.0),
        deadline_at=started_at + timedelta(seconds=60),
    )
    session = SimulationRunner().start(game, spec)
    try:
        while not factory.requests:
            assert session.step().stop_reason is None
    finally:
        session.close()

    deadline = factory.requests[0].deadline_at
    assert deadline is not None
    assert started_at < deadline <= started_at + timedelta(seconds=2.1)


def test_simulation_exposes_structured_discussion_procedure_stages() -> None:
    game = _game()
    factory = _CapturingFactory()
    spec = SimulationSpec(
        "procedure-context",
        "game-1",
        23,
        {player_id: PlayerController(player_id, factory) for player_id in game.snapshot().players},
        response_reference_limit=1,
    )
    session = SimulationRunner().start(game, spec)
    try:
        for _ in range(100):
            assert session.step().stop_reason is None
            procedures = [
                request.observation.procedure
                for request in factory.requests
                if request.observation.procedure is not None
            ]
            if any(procedure.stage_id == "response" for procedure in procedures):
                break
        else:
            pytest.fail("response procedure was not reached")
    finally:
        session.close()

    opening = next(procedure for procedure in procedures if procedure.stage_id == "opening")
    response = next(procedure for procedure in procedures if procedure.stage_id == "response")
    assert (opening.procedure_id, opening.cycle, opening.submission_mode) == (
        "structured_discussion",
        1,
        "sealed",
    )
    assert (response.procedure_id, response.cycle, response.submission_mode) == (
        "structured_discussion",
        1,
        "ordered",
    )
    response_request = next(
        request
        for request in factory.requests
        if request.observation.procedure is not None
        and request.observation.procedure.stage_id == "response"
    )
    speech_option = next(
        option for option in response_request.options if option.action_type == "speech"
    )
    assert len(speech_option.legal_reference_ids) == 1
    speech_actors = {
        str(event.payload["speech_id"]): event.actor_id
        for event in response_request.public_timeline
        if event.event_type == "speech"
    }
    assert all(
        speech_actors[reference_id] != response_request.context.player_id
        for reference_id in speech_option.legal_reference_ids
    )
    speech_topics = {
        str(event.payload["speech_id"]): str(event.payload["topic_id"])
        for event in response_request.public_timeline
        if event.event_type == "speech"
    }
    assert speech_option.legal_topic_ids == tuple(
        dict.fromkeys(speech_topics[item] for item in speech_option.legal_reference_ids)
    )


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
