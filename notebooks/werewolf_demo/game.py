"""Run a deterministic Fake LLM game for the repository quickstart notebook."""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from werewolf_agent.adapters.agents.game_context import build_agent_game_contexts
from werewolf_agent.adapters.agents.game_driver import decide_game_action, langchain_agent_factory
from werewolf_agent.adapters.llm.configuration import LlmProviderConfig
from werewolf_agent.adapters.llm.models import DeliberationLevel, PlayerProfile
from werewolf_agent.adapters.llm.tracing import LlmInvocationTrace
from werewolf_agent.adapters.resources import load_llm_definitions, load_setup_template_catalog
from werewolf_agent.agents import AgentContext, AgentFactory
from werewolf_agent.application.domain_codec import domain_to_data
from werewolf_agent.domain import (
    CompiledRuleSet,
    EventVisibility,
    Game,
    GameEvent,
    GameSetup,
    Phase,
    Player,
    PlayerStatus,
    build_game_rules,
)
from werewolf_agent.setup import (
    checksum_payload,
    generate_players,
    namespace_seed,
    rule_definition_from_values,
)

StopReason = Literal["finished", "max_actions", "max_phases"]
Operation = Literal["action", "advance"]


@dataclass(frozen=True)
class DemoLimits:
    """Bound the amount of work performed by one notebook demonstration."""

    max_phases: int = 64
    max_actions: int = 512

    def __post_init__(self) -> None:
        """Require positive execution limits."""
        if self.max_phases < 1:
            raise ValueError("max_phases must be at least 1")
        if self.max_actions < 1:
            raise ValueError("max_actions must be at least 1")


@dataclass(frozen=True)
class DemoDecision:
    """Safe metadata retained from one Fake LLM invocation."""

    provider: str
    model: str
    phase: str
    day: int
    validation_status: str
    fallback_used: bool
    provider_error: bool


@dataclass(frozen=True)
class DemoStep:
    """One bounded game operation without unresolved private details."""

    operation: Operation
    day: int
    phase: str
    actor_id: str | None
    action_type: str | None
    private_actor_omitted: bool
    private_target_omitted: bool
    public_events: tuple[GameEvent, ...]
    decision: DemoDecision | None = None


@dataclass(frozen=True)
class DemoResult:
    """Safe deterministic summary of a completed or bounded demonstration."""

    completed: bool
    stop_reason: StopReason
    day: int
    winner_id: str | None
    action_count: int
    phase_count: int
    public_events: tuple[GameEvent, ...]
    decisions: tuple[DemoDecision, ...]
    checksum: str


@dataclass
class _SummaryTraceSink:
    decisions: list[DemoDecision] = field(default_factory=list)

    def record_invocation(self, trace: LlmInvocationTrace) -> None:
        """Retain only metadata that cannot expose prompts or private decisions."""
        self.decisions.append(
            DemoDecision(
                provider=trace.provider,
                model=trace.model,
                phase=trace.phase,
                day=trace.day,
                validation_status=trace.validation_status,
                fallback_used=trace.fallback_used,
                provider_error=bool(trace.provider_error),
            )
        )


@dataclass
class FakeGameDemo:
    """Notebook composition root for one deterministic Fake LLM game."""

    game: Game
    rules: CompiledRuleSet
    limits: DemoLimits
    seed: int
    _factories: Mapping[str, AgentFactory]
    _gameplay_random: random.Random
    _trace_sink: _SummaryTraceSink
    _public_events: list[GameEvent]
    _setup_document: Mapping[str, object]
    _setup_checksum: str
    _mechanics_checksum: str
    _player_index: int = 0
    _action_count: int = 0
    _phase_count: int = 0

    @classmethod
    def create(
        cls,
        *,
        template_id: str = "standard_6",
        seed: int = 7,
        deliberation_level: Literal["quick", "standard", "deep"] = "standard",
        limits: DemoLimits | None = None,
    ) -> FakeGameDemo:
        """Create a configured game without environment variables or external services."""
        catalog = load_setup_template_catalog()
        setup = catalog.require_document(template_id)
        mechanics = setup.mechanics
        player_count = sum(mechanics.role_counts.values())
        generated = generate_players(
            setup.player_generation,
            player_count=player_count,
            seed=seed,
        )
        rule_definition = rule_definition_from_values(
            player_count=player_count,
            role_counts=mechanics.role_counts,
            rules=mechanics.rules.to_mapping(),
            roles={role_id: role.to_mapping() for role_id, role in mechanics.roles.items()},
            abilities={
                ability_id: ability.to_mapping()
                for ability_id, ability in mechanics.abilities.items()
            },
        )
        rules = build_game_rules(rule_definition)
        game = Game.create(
            GameSetup(
                players=tuple(
                    Player(id=player.player_id, name=player.profile.name) for player in generated
                )
            ),
            rules=rules,
            random=random.Random(namespace_seed(seed, "role_assignment")),
        )
        profiles = {
            player.player_id: PlayerProfile.model_validate(player.profile.to_mapping())
            for player in generated
        }
        trace_sink = _SummaryTraceSink()
        definitions = load_llm_definitions(prompt_path=None, fake_responses_path=None)
        factories = {
            player_id: langchain_agent_factory(
                _fake_provider_config(),
                definitions=definitions,
                profile=profile,
                trace_sink=trace_sink,
                deliberation_level=DeliberationLevel(deliberation_level),
            )
            for player_id, profile in profiles.items()
        }
        creation_events = [
            event for event in game.creation_events if event.visibility is EventVisibility.PUBLIC
        ]
        setup_document = setup.to_mapping()
        return cls(
            game=game,
            rules=rules,
            limits=limits or DemoLimits(),
            seed=seed,
            _factories=factories,
            _gameplay_random=random.Random(namespace_seed(seed, "gameplay")),
            _trace_sink=trace_sink,
            _public_events=creation_events,
            _setup_document=setup_document,
            _setup_checksum=checksum_payload(setup_document),
            _mechanics_checksum=checksum_payload(mechanics.to_mapping()),
        )

    @property
    def public_events(self) -> tuple[GameEvent, ...]:
        """Return public events emitted so far."""
        return tuple(self._public_events)

    @property
    def decisions(self) -> tuple[DemoDecision, ...]:
        """Return safe Fake LLM invocation summaries."""
        return tuple(self._trace_sink.decisions)

    def step(self) -> DemoStep | None:
        """Perform one action or phase transition unless the game is finished or bounded."""
        if self._stop_reason() is not None:
            return None
        snapshot = self.game.snapshot()
        players = tuple(snapshot.players.values())
        while self._player_index < len(players):
            player = players[self._player_index]
            if player.status is not PlayerStatus.ALIVE:
                self._player_index += 1
                continue
            observation = self.game.view_for(player.id)
            if not observation.available_actions:
                self._player_index += 1
                continue
            decision_index = len(self._trace_sink.decisions)
            decision_seed = namespace_seed(
                self.seed,
                f"demo:{snapshot.day}:{snapshot.phase.value}:{player.id}:{self._action_count}",
            )
            context = AgentContext(
                session_id=f"demo:{self.seed}:{player.id}",
                game_id=f"demo:{self.seed}",
                player_id=player.id,
                session_seed=namespace_seed(self.seed, f"demo-session:{player.id}"),
            )
            game_contexts = build_agent_game_contexts(
                self._setup_document,
                snapshot,
                setup_checksum=self._setup_checksum,
                mechanics_checksum=self._mechanics_checksum,
            )
            action = decide_game_action(
                self._factories[player.id],
                context=context,
                observation=observation,
                decision_seed=decision_seed,
                game_context=game_contexts.get(player.id),
            )
            emitted = self.game.submit(action)
            public_events = self._public(emitted)
            self._action_count += 1
            if not self.game.view_for(player.id).available_actions:
                self._player_index += 1
            is_public_action = action.type.value == "speech"
            return DemoStep(
                operation="action",
                day=snapshot.day,
                phase=snapshot.phase.value,
                actor_id=action.player_id if is_public_action else None,
                action_type=action.type.value,
                private_actor_omitted=not is_public_action,
                private_target_omitted=not is_public_action and action.target_id is not None,
                public_events=public_events,
                decision=self._trace_sink.decisions[decision_index],
            )
        emitted = self.game.advance(self._gameplay_random)
        public_events = self._public(emitted)
        self._phase_count += 1
        self._player_index = 0
        return DemoStep(
            operation="advance",
            day=snapshot.day,
            phase=snapshot.phase.value,
            actor_id=None,
            action_type=None,
            private_actor_omitted=False,
            private_target_omitted=False,
            public_events=public_events,
        )

    def run(self) -> DemoResult:
        """Run until completion or a configured limit and return a safe summary."""
        while self.step() is not None:
            pass
        snapshot = self.game.snapshot()
        stop_reason = self._stop_reason()
        if stop_reason is None:
            raise RuntimeError("demo stopped without a terminal reason")
        payload = {
            "completed": snapshot.is_finished,
            "stop_reason": stop_reason,
            "day": snapshot.day,
            "winner_id": snapshot.winner_id,
            "action_count": self._action_count,
            "phase_count": self._phase_count,
            "public_events": [domain_to_data(event) for event in self._public_events],
            "decisions": [
                {
                    "provider": decision.provider,
                    "model": decision.model,
                    "phase": decision.phase,
                    "day": decision.day,
                    "validation_status": decision.validation_status,
                    "fallback_used": decision.fallback_used,
                    "provider_error": decision.provider_error,
                }
                for decision in self._trace_sink.decisions
            ],
        }
        return DemoResult(
            completed=snapshot.is_finished,
            stop_reason=stop_reason,
            day=snapshot.day,
            winner_id=snapshot.winner_id,
            action_count=self._action_count,
            phase_count=self._phase_count,
            public_events=tuple(self._public_events),
            decisions=tuple(self._trace_sink.decisions),
            checksum=checksum_payload(payload),
        )

    def _public(self, events: list[GameEvent]) -> tuple[GameEvent, ...]:
        public = tuple(event for event in events if event.visibility is EventVisibility.PUBLIC)
        self._public_events.extend(public)
        return public

    def _stop_reason(self) -> StopReason | None:
        if self.game.snapshot().phase is Phase.FINISHED:
            return "finished"
        if self._action_count >= self.limits.max_actions:
            return "max_actions"
        if self._phase_count >= self.limits.max_phases:
            return "max_phases"
        return None


def _fake_provider_config() -> LlmProviderConfig:
    return LlmProviderConfig(
        provider="fake",
        model="fake-list-chat-model",
        base_url="",
        api_key="",
        timeout_seconds=12,
        max_retries=0,
        max_tokens=128,
        temperature=0,
    )
