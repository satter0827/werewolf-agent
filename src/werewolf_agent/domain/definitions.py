"""Configuration-independent definitions for composing game rules."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from werewolf_agent.domain._model import frozen_mapping
from werewolf_agent.domain.rules.base import (
    ActionPolicy,
    PhasePolicy,
    ResolutionPolicy,
    VictoryPolicy,
    VisibilityPolicy,
)
from werewolf_agent.domain.state import (
    AbilityDefinition,
    GameConfig,
    LocalRules,
    Phase,
    RoleCatalog,
)


@dataclass(frozen=True)
class RuleSetDefinition:
    """Validated data used to compose one executable rule set."""

    player_count: int
    role_counts: Mapping[str, int]
    rules: LocalRules
    roles: RoleCatalog
    abilities: Mapping[str, AbilityDefinition]
    phases: tuple[str, ...] = ("night", "day_discussion", "voting")
    action_policy: str = "standard"
    resolution_policy: str = "standard"
    phase_policy: str = "required_actions"
    victory_policy: str = "faction_balance"
    visibility_policy: str = "standard"

    def __post_init__(self) -> None:
        """Freeze nested rule definition values."""
        object.__setattr__(self, "role_counts", frozen_mapping(self.role_counts))
        object.__setattr__(self, "abilities", frozen_mapping(self.abilities))
        object.__setattr__(self, "phases", tuple(self.phases))


@dataclass(frozen=True)
class RuleSet:
    """Executable policies and values for one game."""

    config: GameConfig
    action: ActionPolicy
    resolution: ResolutionPolicy
    phase: PhasePolicy
    victory: VictoryPolicy
    visibility: VisibilityPolicy


PolicyFactory = Callable[[], object]


class RuleRegistry:
    """Explicit registry for supported rule algorithms."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._action: dict[str, Callable[[], ActionPolicy]] = {}
        self._resolution: dict[str, Callable[[], ResolutionPolicy]] = {}
        self._phase: dict[str, Callable[[], PhasePolicy]] = {}
        self._victory: dict[str, Callable[[], VictoryPolicy]] = {}
        self._visibility: dict[str, Callable[[], VisibilityPolicy]] = {}

    @classmethod
    def standard(cls) -> RuleRegistry:
        """Return a registry containing the built-in rule algorithms."""
        from werewolf_agent.domain.policies import (
            FactionBalanceVictoryPolicy,
            RequiredActionsPhasePolicy,
            StandardActionPolicy,
            StandardResolutionPolicy,
            StandardVisibilityPolicy,
        )

        registry = cls()
        registry.register_action("standard", StandardActionPolicy)
        registry.register_resolution("standard", StandardResolutionPolicy)
        registry.register_phase("required_actions", RequiredActionsPhasePolicy)
        registry.register_victory("faction_balance", FactionBalanceVictoryPolicy)
        registry.register_visibility("standard", StandardVisibilityPolicy)
        return registry

    def register_action(self, policy_id: str, factory: Callable[[], ActionPolicy]) -> None:
        """Register an action policy factory."""
        self._action[policy_id] = factory

    def register_resolution(
        self,
        policy_id: str,
        factory: Callable[[], ResolutionPolicy],
    ) -> None:
        """Register a resolution policy factory."""
        self._resolution[policy_id] = factory

    def register_phase(self, policy_id: str, factory: Callable[[], PhasePolicy]) -> None:
        """Register a phase policy factory."""
        self._phase[policy_id] = factory

    def register_victory(self, policy_id: str, factory: Callable[[], VictoryPolicy]) -> None:
        """Register a victory policy factory."""
        self._victory[policy_id] = factory

    def register_visibility(
        self,
        policy_id: str,
        factory: Callable[[], VisibilityPolicy],
    ) -> None:
        """Register a visibility policy factory."""
        self._visibility[policy_id] = factory

    def build(self, definition: RuleSetDefinition) -> RuleSet:
        """Build one rule set or fail for an unregistered policy id."""
        config = GameConfig(
            player_count=definition.player_count,
            role_counts=definition.role_counts,
            rules=definition.rules,
            roles=definition.roles,
            abilities=definition.abilities,
            phase_order=tuple(Phase(phase) for phase in definition.phases),
        )
        try:
            return RuleSet(
                config=config,
                action=self._action[definition.action_policy](),
                resolution=self._resolution[definition.resolution_policy](),
                phase=self._phase[definition.phase_policy](),
                victory=self._victory[definition.victory_policy](),
                visibility=self._visibility[definition.visibility_policy](),
            )
        except KeyError as exc:
            raise ValueError(f"Unknown rule policy: {exc.args[0]}") from exc


__all__ = ["RuleRegistry", "RuleSet", "RuleSetDefinition"]
