"""一局の決定的なstep実行を所有するSimulation Sessionを定義する."""

from __future__ import annotations

import random
import time
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
    ObservedPlayer,
    PublicTimelineEvent,
)
from werewolf_agent.domain import (
    Action,
    CompiledRuleSet,
    Game,
    GameEvent,
    GameSetup,
    GameState,
    GameView,
    SpeechAct,
)
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
        response, trace = self._decide(controller, context, request)
        if self._cancellation.is_cancelled:
            return self._record_stop(
                SimulationStepKind.CANCELLED,
                SimulationStopReason.CANCELLED,
            )
        action = _action_from_response(controller.player_id, response)
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
                timeout_seconds=self._spec.limits.decision_timeout_seconds,
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
            fallback = self._fallback_sessions.get(controller.player_id)
            if fallback is None:
                fallback = controller.fallback_factory.create(context)
                self._fallback_sessions[controller.player_id] = fallback
            response = self._executor.decide(
                fallback,
                request,
                timeout_seconds=self._spec.limits.decision_timeout_seconds,
            )
            _require_legal_response(request, response)
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
        evidence_ids = _latest_speech_ids_by_actor(public_timeline)
        subject_ids = tuple(
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
                    legal_subject_ids=subject_ids if action.type.value == "speech" else (),
                    legal_evidence_ids=(
                        legal_reference_ids
                        if action.type.value == "speech" and legal_reference_ids
                        else evidence_ids
                        if action.type.value in {"speech", "vote"}
                        else ()
                    ),
                    legal_reference_ids=(
                        legal_reference_ids if action.type.value == "speech" else ()
                    ),
                    message_max_chars=(
                        min(
                            self._game.snapshot().config.discussion.message_max_chars,
                            self._spec.speech_message_max_chars
                            or self._game.snapshot().config.discussion.message_max_chars,
                        )
                        if action.type.value == "speech"
                        else None
                    ),
                )
                for action in observation.available_actions
            ),
            decision_seed=seed,
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
    for index, speech in enumerate(observation.history.speeches):
        items.append(
            (
                speech.day,
                index,
                "speech",
                speech.player_id,
                {
                    "message": speech.message,
                    "speech_act": speech.speech_act.value,
                    "subject_id": speech.subject_id,
                    "evidence_id": speech.evidence_id,
                    "speech_id": speech.speech_id,
                    "round_id": speech.round_id,
                    "round_kind": speech.round_kind.value,
                    "response_to_id": speech.response_to_id,
                },
            )
        )
    offset = len(observation.history.speeches)
    for index, vote in enumerate(observation.history.votes):
        items.append(
            (
                vote.day,
                offset + index,
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


def _latest_speech_ids_by_actor(
    public_timeline: tuple[PublicTimelineEvent, ...],
) -> tuple[str, ...]:
    """各話者の最新発言だけを時系列順の根拠候補として返す."""
    selected: list[str] = []
    seen_actors: set[str] = set()
    for event in reversed(public_timeline):
        speech_id = event.payload.get("speech_id")
        if (
            event.event_type == "speech"
            and event.actor_id is not None
            and event.actor_id not in seen_actors
            and speech_id
        ):
            seen_actors.add(event.actor_id)
            selected.append(str(speech_id))
    return tuple(reversed(selected))


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
    if response.action_type == "speech" and response.message is None:
        raise AgentDecisionError("agent_message_required")
    if response.action_type == "speech":
        if response.speech_act not in {
            "question",
            "answer",
            "support",
            "challenge",
            "revise",
        }:
            raise AgentDecisionError("agent_speech_act_required")
        if option.legal_reference_ids and response.speech_act == "question":
            raise AgentDecisionError("agent_response_must_advance_exchange")
        if not option.legal_reference_ids and response.speech_act == "answer":
            raise AgentDecisionError("agent_opening_answer_not_allowed")
        if (
            not option.legal_reference_ids
            and response.speech_act != "question"
            and response.evidence_id is None
        ):
            raise AgentDecisionError("agent_opening_evidence_required")
        if (
            response.evidence_id is not None
            and response.evidence_id not in option.legal_evidence_ids
        ):
            raise AgentDecisionError("agent_evidence_not_legal")
        if response.subject_id not in option.legal_subject_ids:
            raise AgentDecisionError("agent_subject_not_legal")
    if (
        response.message is not None
        and option.message_max_chars is not None
        and len(response.message) > option.message_max_chars
    ):
        raise AgentDecisionError("agent_message_too_long")
    if response.action_type != "speech" and response.message is not None:
        raise AgentDecisionError("agent_message_not_allowed")
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
            referenced_message = next(
                str(event.payload.get("message") or "")
                for event in request.public_timeline
                if event.payload.get("speech_id") == response.response_to_id
            )
            if (
                " ".join(referenced_message.split()).casefold()
                == " ".join((response.message or "").split()).casefold()
            ):
                raise AgentDecisionError("agent_response_must_contribute_new_content")
    elif response.response_to_id is not None:
        raise AgentDecisionError("agent_reference_not_allowed")
    if response.action_type == "vote" and response.reason is None:
        raise AgentDecisionError("agent_vote_reason_required")
    if (
        response.action_type == "vote"
        and option.legal_evidence_ids
        and response.evidence_id not in option.legal_evidence_ids
    ):
        raise AgentDecisionError("agent_vote_evidence_required")
    if (
        response.action_type == "vote"
        and response.evidence_id is not None
        and response.target_id is not None
    ):
        evidence_event = next(
            event
            for event in request.public_timeline
            if event.payload.get("speech_id") == response.evidence_id
        )
        if response.target_id not in {
            evidence_event.actor_id,
            evidence_event.payload.get("subject_id"),
        }:
            raise AgentDecisionError("agent_vote_evidence_target_mismatch")
    if response.action_type != "vote" and response.reason is not None:
        raise AgentDecisionError("agent_vote_reason_not_allowed")


def _action_from_response(player_id: str, response: DecisionResponse) -> Action:
    if response.action_type == "speech":
        if response.message is None or response.speech_act is None or response.subject_id is None:
            raise AgentDecisionError("agent_speech_payload_required")
        return Action.speech(
            player_id,
            response.message,
            speech_act=SpeechAct(response.speech_act),
            subject_id=response.subject_id,
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


def _elapsed_milliseconds(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1_000))


__all__ = [
    "CancellationToken",
    "SimulationRunner",
    "SimulationSession",
    "SynchronousDecisionExecutor",
]
