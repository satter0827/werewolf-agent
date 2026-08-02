"""一局の決定的なstep実行を所有するSimulation Sessionを定義する."""

from __future__ import annotations

import random
import time
from datetime import UTC, datetime, timedelta
from threading import Lock

from werewolf_agent.agents import (
    AgentContext,
    AgentDecisionError,
    AgentObservation,
    AgentProcedure,
    AgentSession,
    DecisionOption,
    DecisionRequest,
    DecisionResponse,
    DecisionTrace,
    EvidenceOption,
    ObservedPlayer,
    PublicTimelineEvent,
)
from werewolf_agent.domain import (
    Action,
    CompiledRuleSet,
    DiscussionPosition,
    DiscussionRelation,
    Game,
    GameEvent,
    GameSetup,
    GameState,
    GameView,
)
from werewolf_agent.domain.discussion_text import normalize_discussion_utterance
from werewolf_agent.setup import namespace_seed
from werewolf_agent.simulation.contracts import (
    AgentMetadata,
    DecisionExecutor,
    DecisionTraceSink,
    NullDecisionTraceSink,
    PlayerController,
    SimulationResult,
    SimulationSpec,
    SimulationStep,
    SimulationStepKind,
    SimulationStopReason,
)


class CancellationToken:
    """外部から安全に停止要求を伝える小さな同期境界."""

    def __init__(self) -> None:
        """未cancelのtokenを作成する."""
        self._cancelled = False
        self._lock = Lock()

    def cancel(self) -> None:
        """以後のstep開始を停止する."""
        with self._lock:
            self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        """停止要求済みか返す."""
        with self._lock:
            return self._cancelled


class _SimulationDeadlineReached(Exception):
    """Signal that no fallback may start after the full-run deadline."""


class SynchronousDecisionExecutor:
    """Agentを同じthreadで一回だけ呼び出す既定executor."""

    def decide(
        self,
        session: AgentSession,
        request: DecisionRequest,
        *,
        timeout_seconds: float | None,
    ) -> DecisionResponse:
        """応答後に経過時間を検査し、不完全なthread中断を行わない."""
        started_at = time.perf_counter()
        response = session.decide(request)
        elapsed = time.perf_counter() - started_at
        if timeout_seconds is not None and elapsed > timeout_seconds:
            raise AgentDecisionError(
                "agent_timeout",
                {"elapsed_seconds": elapsed, "timeout_seconds": timeout_seconds},
            )
        return response


class SimulationSession:
    """一局のGameとAgent Sessionを所有し、一回ずつ進行させる."""

    def __init__(
        self,
        game: Game,
        spec: SimulationSpec,
        *,
        decision_executor: DecisionExecutor | None = None,
        trace_sink: DecisionTraceSink | None = None,
        cancellation: CancellationToken | None = None,
        resume_from: SimulationResult | None = None,
    ) -> None:
        """一局の依存と実行位置を初期化する."""
        self._game = game
        self._spec = spec
        self._executor = (
            decision_executor if decision_executor is not None else SynchronousDecisionExecutor()
        )
        self._trace_sink = trace_sink if trace_sink is not None else NullDecisionTraceSink()
        self._cancellation = cancellation if cancellation is not None else CancellationToken()
        self._agent_sessions: dict[str, AgentSession] = {}
        self._fallback_sessions: dict[str, AgentSession] = {}
        self._steps = list(resume_from.steps) if resume_from is not None else []
        self._action_count = resume_from.action_count if resume_from is not None else 0
        self._phase_count = resume_from.phase_count if resume_from is not None else 0
        self._closed = False
        state = game.snapshot()
        player_ids = set(state.players)
        if set(spec.controllers) != player_ids:
            raise ValueError("controllers must exactly match game players")
        if resume_from is not None:
            _validate_resume_result(resume_from, spec=spec, state=state)

    @property
    def game(self) -> Game:
        """所有するGameをheadless利用者へ返す."""
        return self._game

    @property
    def spec(self) -> SimulationSpec:
        """一局へ固定した実行仕様を返す."""
        return self._spec

    @property
    def steps(self) -> tuple[SimulationStep, ...]:
        """現在までのimmutable step列を返す."""
        return tuple(self._steps)

    def step(self) -> SimulationStep:
        """Agent action、phase進行、または停止判定を一つだけ実行する."""
        self._require_open()
        terminal = self._terminal_step()
        if terminal is not None:
            return terminal

        manual_pending = False
        for player_id in self._game.snapshot().players:
            observation = self._game.view_for(player_id)
            if not observation.available_actions:
                continue
            controller = self._spec.controllers[player_id]
            if controller.is_manual:
                manual_pending = True
                continue
            if self._action_count >= self._spec.limits.max_actions:
                return self._record_stop(
                    SimulationStepKind.LIMIT_REACHED,
                    SimulationStopReason.ACTION_LIMIT,
                )
            return self._agent_action(controller, observation)

        if manual_pending:
            if self._action_count >= self._spec.limits.max_actions:
                return self._record_stop(
                    SimulationStepKind.LIMIT_REACHED,
                    SimulationStopReason.ACTION_LIMIT,
                )
            return self._record_stop(
                SimulationStepKind.WAITING_FOR_MANUAL,
                SimulationStopReason.WAITING_FOR_MANUAL,
            )
        return self._advance_phase()

    def submit_manual(self, action: Action) -> SimulationStep:
        """Manual controllerの一つのactionを検証して適用する."""
        self._require_open()
        terminal = self._terminal_step()
        if terminal is not None:
            raise RuntimeError(f"simulation cannot accept input: {terminal.stop_reason}")
        if self._action_count >= self._spec.limits.max_actions:
            raise RuntimeError("simulation cannot accept input: action_limit")
        controller = self._spec.controllers.get(action.player_id)
        if controller is None or not controller.is_manual:
            raise ValueError("manual action requires a manual player controller")
        before = self._game.snapshot()
        events = tuple(self._game.submit(action))
        self._action_count += 1
        return self._record(
            SimulationStepKind.MANUAL_ACTION,
            before=before,
            events=events,
            actor_id=action.player_id,
            action_type=action.type.value,
        )

    def run(self) -> SimulationResult:
        """明示的な停止理由へ到達するまでstepを繰り返す."""
        while True:
            step = self.step()
            if step.stop_reason is not None:
                return self.result(step.stop_reason)

    def result(self, stop_reason: SimulationStopReason) -> SimulationResult:
        """現在位置を再開可能な結果として返す."""
        return SimulationResult(
            spec=self._spec,
            stop_reason=stop_reason,
            state=self._game.snapshot(),
            steps=tuple(self._steps),
            action_count=self._action_count,
            phase_count=self._phase_count,
        )

    def close(self) -> None:
        """所有する全Agent Sessionを冪等に解放する."""
        if self._closed:
            return
        self._closed = True
        for session in (*self._agent_sessions.values(), *self._fallback_sessions.values()):
            session.close()

    def _terminal_step(self) -> SimulationStep | None:
        if self._cancellation.is_cancelled:
            return self._record_stop(SimulationStepKind.CANCELLED, SimulationStopReason.CANCELLED)
        state = self._game.snapshot()
        if state.is_finished:
            return self._record_stop(SimulationStepKind.FINISHED, SimulationStopReason.FINISHED)
        if _deadline_expired(self._spec):
            return self._record_stop(
                SimulationStepKind.DEADLINE_REACHED,
                SimulationStopReason.DEADLINE_REACHED,
            )
        limits = self._spec.limits
        if self._phase_count >= limits.max_phases:
            return self._record_stop(
                SimulationStepKind.LIMIT_REACHED,
                SimulationStopReason.PHASE_LIMIT,
            )
        return None

    def _agent_action(
        self,
        controller: PlayerController,
        observation: GameView,
    ) -> SimulationStep:
        before = self._game.snapshot()
        context = self._agent_context(controller.player_id)
        request = self._decision_request(context, controller, observation)
        if _deadline_expired(self._spec):
            return self._record_stop(
                SimulationStepKind.DEADLINE_REACHED,
                SimulationStopReason.DEADLINE_REACHED,
            )
        try:
            response, trace = self._decide(controller, context, request)
        except _SimulationDeadlineReached:
            return self._record_stop(
                SimulationStepKind.DEADLINE_REACHED,
                SimulationStopReason.DEADLINE_REACHED,
            )
        if self._cancellation.is_cancelled:
            return self._record_stop(
                SimulationStepKind.CANCELLED,
                SimulationStopReason.CANCELLED,
            )
        if _deadline_expired(self._spec):
            return self._record_stop(
                SimulationStepKind.DEADLINE_REACHED,
                SimulationStopReason.DEADLINE_REACHED,
            )
        action = action_from_response(controller.player_id, response)
        events = tuple(self._game.submit(action))
        self._action_count += 1
        return self._record(
            SimulationStepKind.AGENT_ACTION,
            before=before,
            events=events,
            actor_id=controller.player_id,
            action_type=action.type.value,
            decision_trace=trace,
        )

    def _advance_phase(self) -> SimulationStep:
        before = self._game.snapshot()
        phase_seed = (
            self._spec.phase_seed
            if self._spec.phase_seed is not None
            else namespace_seed(self._spec.seed, "simulation:phase")
        )
        phase_random = random.Random(
            namespace_seed(phase_seed, f"simulation:phase:{self._phase_count + 1}")
        )
        events = tuple(self._game.advance(phase_random))
        self._phase_count += 1
        return self._record(SimulationStepKind.PHASE_ADVANCED, before=before, events=events)

    def _decide(
        self,
        controller: PlayerController,
        context: AgentContext,
        request: DecisionRequest,
    ) -> tuple[DecisionResponse, DecisionTrace]:
        assert controller.factory is not None
        started_at = time.perf_counter()
        try:
            session = self._agent_sessions.get(controller.player_id)
            if session is None:
                session = controller.factory.create(context)
                self._agent_sessions[controller.player_id] = session
            response = self._executor.decide(
                session,
                request,
                timeout_seconds=_effective_timeout(self._spec, request),
            )
            _require_legal_response(request, response)
            trace = DecisionTrace(
                decision_id=request.decision_id,
                agent_spec=controller.factory.spec,
                response=response,
                latency_ms=_elapsed_milliseconds(started_at),
            )
        except Exception as exc:
            error = (
                exc
                if isinstance(exc, AgentDecisionError)
                else AgentDecisionError(
                    "agent_decision_failed",
                    {"error_type": type(exc).__name__},
                )
            )
            if _request_deadline_expired(request):
                trace = DecisionTrace(
                    decision_id=request.decision_id,
                    agent_spec=controller.factory.spec,
                    response=None,
                    latency_ms=_elapsed_milliseconds(started_at),
                    error_code=error.code,
                    diagnostics=error.diagnostics,
                )
                self._trace_sink.record_decision(trace)
                raise _SimulationDeadlineReached from exc
            fallback = self._fallback_sessions.get(controller.player_id)
            if fallback is None:
                fallback = controller.fallback_factory.create(context)
                self._fallback_sessions[controller.player_id] = fallback
            try:
                response = self._executor.decide(
                    fallback,
                    request,
                    timeout_seconds=_effective_timeout(self._spec, request),
                )
                _require_legal_response(request, response)
            except Exception as fallback_exc:
                fallback_error = (
                    fallback_exc
                    if isinstance(fallback_exc, AgentDecisionError)
                    else AgentDecisionError(
                        "agent_fallback_failed",
                        {"error_type": type(fallback_exc).__name__},
                    )
                )
                if _request_deadline_expired(request) or fallback_error.code == "agent_timeout":
                    trace = DecisionTrace(
                        decision_id=request.decision_id,
                        agent_spec=controller.fallback_factory.spec,
                        response=None,
                        latency_ms=_elapsed_milliseconds(started_at),
                        error_code=fallback_error.code,
                        diagnostics={
                            **fallback_error.diagnostics,
                            "primary_error_code": error.code,
                            "primary_diagnostics": error.diagnostics,
                        },
                    )
                    self._trace_sink.record_decision(trace)
                    raise _SimulationDeadlineReached from fallback_exc
                raise
            trace = DecisionTrace(
                decision_id=request.decision_id,
                agent_spec=controller.fallback_factory.spec,
                response=response,
                latency_ms=_elapsed_milliseconds(started_at),
                fallback_used=True,
                error_code=error.code,
                diagnostics=error.diagnostics,
            )
        self._trace_sink.record_decision(trace)
        return response, trace

    def _agent_context(self, player_id: str) -> AgentContext:
        return AgentContext(
            session_id=f"{self._spec.simulation_id}:{player_id}",
            game_id=self._spec.game_id,
            player_id=player_id,
            session_seed=namespace_seed(
                self._spec.seed,
                f"simulation:session:{player_id}",
            ),
        )

    def _decision_request(
        self,
        context: AgentContext,
        controller: PlayerController,
        observation: GameView,
    ) -> DecisionRequest:
        seed = namespace_seed(
            self._spec.seed,
            (
                f"simulation:decision:{self._action_count}:{context.player_id}:"
                f"{observation.phase.value}:{observation.day}"
            ),
        )
        players = tuple(
            ObservedPlayer(player.id, player.name, player.status.value == "alive")
            for player in observation.players
        )
        me = next(player for player in players if player.player_id == observation.me.id)
        metadata = (
            controller.metadata_provider.resolve(observation)
            if controller.metadata_provider is not None
            else AgentMetadata(controller.identity, controller.world)
        )
        if not isinstance(metadata, AgentMetadata):
            raise TypeError("metadata provider must return AgentMetadata")
        public_timeline = _public_timeline(observation)
        reference_evidence_options = _evidence_options(public_timeline)
        vote_evidence_options = tuple(
            EvidenceOption(
                evidence_id=item.evidence_id,
                kind=item.kind.value,
                actor_id=item.actor_id,
                topic_id=item.topic_id,
                position=None if item.position is None else item.position.value,
            )
            for item in observation.legal_evidence.get("vote", ())
        )
        opening_topic_ids = tuple(
            player.player_id
            for player in players
            if player.player_id != context.player_id and player.alive
        )
        discussion_round = observation.discussion_round
        legal_reference_ids: tuple[str, ...] = ()
        if discussion_round is not None:
            legal_reference_ids = tuple(
                reference_id
                for reference_id in discussion_round.reference_ids
                if next(
                    speech.player_id
                    for speech in observation.history.speeches
                    if speech.speech_id == reference_id
                )
                != context.player_id
            )
        if legal_reference_ids and self._spec.response_reference_limit is not None:
            if discussion_round is None:
                raise RuntimeError("discussion references require an active round")
            actor_index = discussion_round.actor_order.index(context.player_id)
            offset = actor_index % len(legal_reference_ids)
            rotated_references = (*legal_reference_ids[offset:], *legal_reference_ids[:offset])
            legal_reference_ids = rotated_references[: self._spec.response_reference_limit]
        topic_ids = (
            tuple(
                dict.fromkeys(
                    speech.topic_id
                    for speech in observation.history.speeches
                    if speech.speech_id in legal_reference_ids
                )
            )
            if legal_reference_ids
            else opening_topic_ids
        )
        discussion_config = self._game.snapshot().config.discussion
        active_discussion_stage = (
            next(
                stage for stage in discussion_config.stages if stage.stage is discussion_round.kind
            )
            if discussion_round is not None
            else None
        )
        return DecisionRequest(
            decision_id=(
                f"{context.session_id}:{observation.phase.value}:{observation.day}:"
                f"{self._action_count + 1}"
            ),
            context=context,
            observation=AgentObservation(
                phase=observation.phase.value,
                day=observation.day,
                me=me,
                players=players,
                known_roles=dict(observation.known_roles),
                known_factions=dict(observation.known_factions),
                identity=metadata.identity,
                world=metadata.world,
                procedure=(
                    AgentProcedure(
                        procedure_id="structured_discussion",
                        stage_id=observation.discussion_round.kind.value,
                        cycle=observation.discussion_round.cycle,
                        submission_mode=observation.discussion_round.submission_mode.value,
                    )
                    if observation.discussion_round is not None
                    else None
                ),
            ),
            public_timeline=public_timeline,
            options=tuple(
                DecisionOption(
                    action_type=action.type.value,
                    ability_id=action.ability_id,
                    legal_target_ids=tuple(observation.legal_targets.get(action.key, ())),
                    legal_topic_ids=topic_ids if action.type.value == "speech" else (),
                    evidence_options=(
                        tuple(
                            item
                            for item in reference_evidence_options
                            if item.evidence_id in legal_reference_ids
                        )
                        if action.type.value == "speech" and legal_reference_ids
                        else reference_evidence_options
                        if action.type.value == "speech"
                        else vote_evidence_options
                        if action.type.value == "vote"
                        else ()
                    ),
                    legal_reference_ids=(
                        legal_reference_ids if action.type.value == "speech" else ()
                    ),
                    legal_positions=(
                        ("support", "oppose", "undecided") if action.type.value == "speech" else ()
                    ),
                    legal_relations=(
                        tuple(
                            relation.value for relation in active_discussion_stage.allowed_relations
                        )
                        if action.type.value == "speech" and active_discussion_stage is not None
                        else ()
                    ),
                    message_max_chars=(
                        min(
                            discussion_config.message_max_chars,
                            self._spec.speech_message_max_chars
                            or discussion_config.message_max_chars,
                        )
                        if action.type.value == "speech"
                        else None
                    ),
                    reason_max_chars=(
                        self._game.snapshot().config.voting.reason_max_chars
                        if action.type.value == "vote"
                        else None
                    ),
                )
                for action in observation.available_actions
            ),
            decision_seed=seed,
            deadline_at=_decision_deadline(self._spec),
        )

    def _record_stop(
        self,
        kind: SimulationStepKind,
        reason: SimulationStopReason,
    ) -> SimulationStep:
        state = self._game.snapshot()
        return self._record(kind, before=state, events=(), stop_reason=reason)

    def _record(
        self,
        kind: SimulationStepKind,
        *,
        before: GameState,
        events: tuple[GameEvent, ...],
        actor_id: str | None = None,
        action_type: str | None = None,
        decision_trace: DecisionTrace | None = None,
        stop_reason: SimulationStopReason | None = None,
    ) -> SimulationStep:
        before_state = before
        after = self._game.snapshot()
        step = SimulationStep(
            index=len(self._steps) + 1,
            kind=kind,
            phase_before=before_state.phase.value,
            phase_after=after.phase.value,
            day_before=before_state.day,
            day_after=after.day,
            events=events,
            actor_id=actor_id,
            action_type=action_type,
            decision_trace=decision_trace,
            stop_reason=stop_reason,
        )
        self._steps.append(step)
        return step

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("simulation session is closed")


class SimulationRunner:
    """一局のSimulation Sessionを構築し、必要なら停止まで実行する."""

    def create(
        self,
        setup: GameSetup,
        *,
        rules: CompiledRuleSet,
        spec: SimulationSpec,
        decision_executor: DecisionExecutor | None = None,
        trace_sink: DecisionTraceSink | None = None,
        cancellation: CancellationToken | None = None,
    ) -> SimulationSession:
        """setupと用途分離seedからGameを作成してSessionを開始する."""
        game = Game.create(
            setup,
            rules=rules,
            random=random.Random(namespace_seed(spec.seed, "simulation:role-assignment")),
        )
        return self.start(
            game,
            spec,
            decision_executor=decision_executor,
            trace_sink=trace_sink,
            cancellation=cancellation,
        )

    def restore(
        self,
        result: SimulationResult,
        *,
        rules: CompiledRuleSet,
        decision_executor: DecisionExecutor | None = None,
        trace_sink: DecisionTraceSink | None = None,
        cancellation: CancellationToken | None = None,
    ) -> SimulationSession:
        """再開情報を検証し、乱数位置と実行上限を保ってSessionを復元する."""
        return SimulationSession(
            Game.restore(result.state, rules=rules),
            result.spec,
            decision_executor=decision_executor,
            trace_sink=trace_sink,
            cancellation=cancellation,
            resume_from=result,
        )

    def start(
        self,
        game: Game,
        spec: SimulationSpec,
        *,
        decision_executor: DecisionExecutor | None = None,
        trace_sink: DecisionTraceSink | None = None,
        cancellation: CancellationToken | None = None,
    ) -> SimulationSession:
        """既存または作成直後のGameから再開可能なSessionを開始する."""
        return SimulationSession(
            game,
            spec,
            decision_executor=decision_executor,
            trace_sink=trace_sink,
            cancellation=cancellation,
        )

    def run(self, game: Game, spec: SimulationSpec) -> SimulationResult:
        """resourceを必ず解放して一局を停止理由まで進める."""
        session = self.start(game, spec)
        try:
            return session.run()
        finally:
            session.close()


def _validate_resume_result(
    result: SimulationResult,
    *,
    spec: SimulationSpec,
    state: GameState,
) -> None:
    """改変または別条件のresultを再開位置として受け付けない."""
    if result.spec != spec:
        raise ValueError("result spec must match resumed session spec")
    if result.state != state:
        raise ValueError("result state must match restored game state")
    if tuple(step.index for step in result.steps) != tuple(range(1, len(result.steps) + 1)):
        raise ValueError("result step indexes must be contiguous")
    action_count = sum(
        step.kind in {SimulationStepKind.AGENT_ACTION, SimulationStepKind.MANUAL_ACTION}
        for step in result.steps
    )
    phase_count = sum(step.kind is SimulationStepKind.PHASE_ADVANCED for step in result.steps)
    if result.action_count != action_count:
        raise ValueError("result action count must match steps")
    if result.phase_count != phase_count:
        raise ValueError("result phase count must match steps")
    if result.steps:
        last = result.steps[-1]
        if last.phase_after != state.phase.value or last.day_after != state.day:
            raise ValueError("result final step must match state position")


def _public_timeline(observation: GameView) -> tuple[PublicTimelineEvent, ...]:
    items: list[tuple[int, int, str, str | None, dict[str, object]]] = []
    speeches = {speech.speech_id: speech for speech in observation.history.speeches}
    emitted_speech_ids: set[str] = set()
    event_index = 0
    for discussion in observation.history.discussions:
        round_speeches = {
            speeches[speech_id].player_id: speeches[speech_id]
            for speech_id in discussion.speech_ids
        }
        passed_player_ids = set(discussion.passed_player_ids)
        for player_id in discussion.actor_ids:
            speech = round_speeches.get(player_id)
            if speech is not None:
                event_type = "speech"
                payload: dict[str, object] = {
                    "utterance": speech.utterance,
                    "topic_id": speech.topic_id,
                    "position": speech.position.value,
                    "relation": speech.relation.value,
                    "evidence_id": speech.evidence_id,
                    "speech_id": speech.speech_id,
                    "round_id": speech.round_id,
                    "round_kind": speech.round_kind.value,
                    "response_to_id": speech.response_to_id,
                }
                emitted_speech_ids.add(speech.speech_id)
            elif player_id in passed_player_ids:
                event_type = "discussion_pass"
                payload = {
                    "evidence_id": f"pass:{discussion.day}:{discussion.round_id}:{player_id}",
                    "round_id": discussion.round_id,
                    "round_kind": discussion.kind.value,
                    "topic_id": player_id,
                }
            else:
                raise ValueError("discussion result actor must have a speech or pass")
            items.append((discussion.day, event_index, event_type, player_id, payload))
            event_index += 1
    for speech in observation.history.speeches:
        if speech.speech_id not in emitted_speech_ids:
            raise ValueError("speech history must belong to a resolved discussion round")
    for index, vote in enumerate(observation.history.votes):
        items.append(
            (
                vote.day,
                event_index + index,
                "vote_round",
                None,
                {
                    "votes": dict(vote.votes),
                    "reasons": dict(vote.reasons),
                    "evidence_ids": dict(vote.evidence_ids),
                    "counts": dict(vote.counts),
                    "eliminated_player_id": vote.eliminated_player_id,
                },
            )
        )
    items.sort(key=lambda item: (item[0], item[1]))
    return tuple(
        PublicTimelineEvent(sequence, event_type, day, actor_id, payload)
        for sequence, (day, _, event_type, actor_id, payload) in enumerate(items, start=1)
    )


def _evidence_options(
    public_timeline: tuple[PublicTimelineEvent, ...],
) -> tuple[EvidenceOption, ...]:
    """参照可能な全公開議論事実を時系列順に返す."""
    selected: list[EvidenceOption] = []
    seen_ids: set[str] = set()
    for event in public_timeline:
        evidence_id = event.payload.get("speech_id") or event.payload.get("evidence_id")
        normalized_id = str(evidence_id or "")
        if (
            event.event_type in {"speech", "discussion_pass"}
            and event.actor_id is not None
            and normalized_id
            and normalized_id not in seen_ids
        ):
            seen_ids.add(normalized_id)
            selected.append(
                EvidenceOption(
                    evidence_id=normalized_id,
                    kind=("discussion" if event.event_type == "speech" else "discussion_pass"),
                    actor_id=event.actor_id,
                    topic_id=str(event.payload.get("topic_id") or event.actor_id),
                    position=(
                        str(event.payload["position"])
                        if event.payload.get("position") is not None
                        else None
                    ),
                )
            )
    return tuple(selected)


def _require_legal_response(request: DecisionRequest, response: DecisionResponse) -> None:
    option = next(
        (
            item
            for item in request.options
            if item.action_type == response.action_type and item.ability_id == response.ability_id
        ),
        None,
    )
    if option is None:
        raise AgentDecisionError("agent_action_not_available")
    if response.target_id is not None and response.target_id not in option.legal_target_ids:
        raise AgentDecisionError("agent_target_not_legal")
    if option.legal_target_ids and response.target_id is None:
        raise AgentDecisionError("agent_target_required")
    if response.action_type == "speech" and response.utterance is None:
        raise AgentDecisionError("agent_utterance_required")
    if response.action_type == "speech":
        if response.position not in option.legal_positions:
            raise AgentDecisionError("agent_position_not_legal")
        if response.relation not in option.legal_relations:
            raise AgentDecisionError("agent_relation_not_legal")
        evidence_ids = {item.evidence_id for item in option.evidence_options}
        if response.evidence_id is not None and response.evidence_id not in evidence_ids:
            raise AgentDecisionError("agent_evidence_not_legal")
        if response.topic_id not in option.legal_topic_ids:
            raise AgentDecisionError("agent_topic_not_legal")
    if (
        response.utterance is not None
        and option.message_max_chars is not None
        and len(response.utterance) > option.message_max_chars
    ):
        raise AgentDecisionError("agent_message_too_long")
    if response.action_type != "speech" and response.utterance is not None:
        raise AgentDecisionError("agent_utterance_not_allowed")
    if (
        response.action_type == "vote"
        and response.reason is not None
        and option.reason_max_chars is not None
        and len(response.reason) > option.reason_max_chars
    ):
        raise AgentDecisionError("agent_reason_too_long")
    if response.action_type == "speech":
        if option.legal_reference_ids and response.response_to_id is None:
            raise AgentDecisionError("agent_reference_required")
        if (
            response.response_to_id is not None
            and response.response_to_id not in option.legal_reference_ids
        ):
            raise AgentDecisionError("agent_reference_not_legal")
        if option.legal_reference_ids and response.evidence_id != response.response_to_id:
            raise AgentDecisionError("agent_response_evidence_mismatch")
        if option.legal_reference_ids and response.response_to_id is not None:
            referenced = next(
                event
                for event in request.public_timeline
                if event.payload.get("speech_id") == response.response_to_id
            )
            if response.topic_id != referenced.payload.get("topic_id"):
                raise AgentDecisionError("agent_response_topic_mismatch")
            _require_legal_response_relation(request, response, referenced)
            referenced_message = str(referenced.payload.get("utterance") or "")
            if _normalized_utterance(referenced_message) == _normalized_utterance(
                response.utterance or ""
            ):
                raise AgentDecisionError("agent_response_must_contribute_new_content")
    elif response.response_to_id is not None:
        raise AgentDecisionError("agent_reference_not_allowed")
    if response.action_type == "vote" and response.reason is None:
        raise AgentDecisionError("agent_vote_reason_required")
    if (
        response.action_type == "vote"
        and option.evidence_options
        and response.evidence_id not in {item.evidence_id for item in option.evidence_options}
    ):
        raise AgentDecisionError("agent_vote_evidence_required")
    if (
        response.action_type == "vote"
        and response.evidence_id is not None
        and response.target_id is not None
    ):
        evidence = next(
            item for item in option.evidence_options if item.evidence_id == response.evidence_id
        )
        if response.target_id not in {
            evidence.actor_id,
            evidence.topic_id,
        }:
            raise AgentDecisionError("agent_vote_evidence_target_mismatch")
    if response.action_type != "vote" and response.reason is not None:
        raise AgentDecisionError("agent_vote_reason_not_allowed")


def _normalized_utterance(value: str) -> str:
    """Normalize repetition checks with schema-expressible ASCII case folding."""
    return normalize_discussion_utterance(value)


def _require_legal_response_relation(
    request: DecisionRequest,
    response: DecisionResponse,
    referenced: PublicTimelineEvent,
) -> None:
    """参照発言とresponseのrelation・positionを一つの組合せとして検証する."""
    referenced_position = str(referenced.payload.get("position") or "")
    if response.relation == "answer":
        if referenced_position != "undecided" or response.position == "undecided":
            raise AgentDecisionError("agent_response_answer_mismatch")
        return
    if response.relation == "support":
        if response.position != referenced_position:
            raise AgentDecisionError("agent_response_support_mismatch")
        return
    if response.relation == "challenge":
        if {response.position, referenced_position} != {"support", "oppose"}:
            raise AgentDecisionError("agent_response_challenge_mismatch")
        return
    if response.relation == "revise":
        prior = next(
            (
                event
                for event in reversed(request.public_timeline)
                if event.event_type == "speech"
                and event.actor_id == request.context.player_id
                and event.payload.get("topic_id") == response.topic_id
            ),
            None,
        )
        if prior is None or prior.payload.get("position") == response.position:
            raise AgentDecisionError("agent_response_revision_mismatch")


def action_from_response(player_id: str, response: DecisionResponse) -> Action:
    """検証済みAgent応答をdomainへ提出する正規Actionへ変換する."""
    if response.action_type == "speech":
        if (
            response.utterance is None
            or response.topic_id is None
            or response.position is None
            or response.relation is None
        ):
            raise AgentDecisionError("agent_speech_payload_required")
        return Action.speech(
            player_id,
            response.utterance,
            topic_id=response.topic_id,
            position=DiscussionPosition(response.position),
            relation=DiscussionRelation(response.relation),
            evidence_id=response.evidence_id,
            response_to_id=response.response_to_id,
        )
    if response.action_type == "vote":
        if response.target_id is None:
            raise AgentDecisionError("agent_target_required")
        if response.reason is None:
            raise AgentDecisionError("agent_vote_reason_required")
        return Action.vote(
            player_id,
            response.target_id,
            reason=response.reason,
            evidence_id=response.evidence_id,
        )
    if response.action_type == "use_ability":
        if response.target_id is None or response.ability_id is None:
            raise AgentDecisionError("agent_ability_payload_required")
        return Action.use_ability(player_id, response.ability_id, response.target_id)
    if response.action_type == "pass":
        return Action.pass_(player_id)
    raise AgentDecisionError("agent_action_not_available")


def _effective_timeout(spec: SimulationSpec, request: DecisionRequest) -> float | None:
    """一回の待機上限をcall上限と全体deadlineの短い方へ制限する."""
    timeout = spec.limits.decision_timeout_seconds
    if request.deadline_at is None:
        return timeout
    remaining = max((request.deadline_at - datetime.now(UTC)).total_seconds(), 0.001)
    return remaining if timeout is None else min(timeout, remaining)


def _decision_deadline(spec: SimulationSpec) -> datetime | None:
    """Return one deadline combining the full-run and per-call limits."""
    call_deadline = (
        datetime.now(UTC) + timedelta(seconds=spec.limits.decision_timeout_seconds)
        if spec.limits.decision_timeout_seconds is not None
        else None
    )
    if spec.deadline_at is None:
        return call_deadline
    if call_deadline is None:
        return spec.deadline_at
    return min(spec.deadline_at, call_deadline)


def _deadline_expired(spec: SimulationSpec) -> bool:
    """Return whether the full-run deadline has elapsed."""
    return spec.deadline_at is not None and datetime.now(UTC) >= spec.deadline_at


def _request_deadline_expired(request: DecisionRequest) -> bool:
    """Return whether the effective per-decision deadline has elapsed."""
    return request.deadline_at is not None and datetime.now(UTC) >= request.deadline_at


def _elapsed_milliseconds(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1_000))


__all__ = [
    "CancellationToken",
    "SimulationRunner",
    "SimulationSession",
    "SynchronousDecisionExecutor",
]
