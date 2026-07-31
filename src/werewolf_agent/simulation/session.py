"""一局の決定的なstep実行を所有するSimulation Sessionを定義する."""

from __future__ import annotations

import random
import time
from threading import Lock

from werewolf_agent.agents import (
    AgentContext,
    AgentDecisionError,
    AgentObservation,
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
    ) -> None:
        """一局の依存と実行位置を初期化する."""
        self._game = game
        self._spec = spec
        self._executor = (
            decision_executor if decision_executor is not None else SynchronousDecisionExecutor()
        )
        self._trace_sink = trace_sink if trace_sink is not None else NullDecisionTraceSink()
        self._cancellation = cancellation if cancellation is not None else CancellationToken()
        self._phase_random = random.Random(
            spec.phase_seed
            if spec.phase_seed is not None
            else namespace_seed(spec.seed, "simulation:phase")
        )
        self._agent_sessions: dict[str, AgentSession] = {}
        self._fallback_sessions: dict[str, AgentSession] = {}
        self._steps: list[SimulationStep] = []
        self._action_count = 0
        self._phase_count = 0
        self._closed = False
        player_ids = set(game.snapshot().players)
        if set(spec.controllers) != player_ids:
            raise ValueError("controllers must exactly match game players")

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
            simulation_id=self._spec.simulation_id,
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
        events = tuple(self._game.advance(self._phase_random))
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
                agent_spec=controller.factory.spec,
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
            ),
            public_timeline=_public_timeline(observation),
            options=tuple(
                DecisionOption(
                    action_type=action.type.value,
                    ability_id=action.ability_id,
                    legal_target_ids=tuple(observation.legal_targets.get(action.key, ())),
                    message_max_chars=(
                        self._spec.speech_message_max_chars
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
        state: GameState,
        *,
        rules: CompiledRuleSet,
        spec: SimulationSpec,
        decision_executor: DecisionExecutor | None = None,
        trace_sink: DecisionTraceSink | None = None,
        cancellation: CancellationToken | None = None,
    ) -> SimulationSession:
        """検証済みstateをI/Oなしで復元してSessionを開始する."""
        return self.start(
            Game.restore(state, rules=rules),
            spec,
            decision_executor=decision_executor,
            trace_sink=trace_sink,
            cancellation=cancellation,
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
                    "focus_id": speech.focus_id,
                    "evidence_id": speech.evidence_id,
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
    if (
        response.message is not None
        and option.message_max_chars is not None
        and len(response.message) > option.message_max_chars
    ):
        raise AgentDecisionError("agent_message_too_long")
    if response.action_type != "speech" and response.message is not None:
        raise AgentDecisionError("agent_message_not_allowed")


def _action_from_response(player_id: str, response: DecisionResponse) -> Action:
    if response.action_type == "speech":
        if response.message is None:
            raise AgentDecisionError("agent_message_required")
        return Action.speech(
            player_id,
            response.message,
            focus_id=response.focus_id,
            evidence_id=response.evidence_id,
        )
    if response.action_type == "vote":
        if response.target_id is None:
            raise AgentDecisionError("agent_target_required")
        return Action.vote(player_id, response.target_id)
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
