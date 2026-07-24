"""Configuration-independent definitions for composing game rules."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

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
    GameState,
    LocalRules,
    Phase,
    RoleCatalog,
)


@dataclass(frozen=True)
class RuleSetDefinition:
    """Validated data used to compose one executable rule set."""

    player_count: int
    role_counts: dict[str, int]
    rules: LocalRules
    roles: RoleCatalog
    abilities: dict[str, AbilityDefinition]
    phases: tuple[str, ...] = ("night", "day_discussion", "voting")
    action_policy: str = "standard"
    resolution_policy: str = "standard"
    phase_policy: str = "required_actions"
    victory_policy: str = "faction_balance"
    visibility_policy: str = "standard"

    @classmethod
    def from_values(
        cls,
        *,
        player_count: int,
        role_counts: Mapping[str, int],
        rules: Mapping[str, object],
        roles: Mapping[str, Mapping[str, object]],
        abilities: Mapping[str, Mapping[str, object]],
        composition: Mapping[str, object],
    ) -> RuleSetDefinition:
        """Build a definition from validated external configuration values."""
        return cls(
            player_count=player_count,
            role_counts=dict(role_counts),
            rules=LocalRules.model_validate(rules),
            roles=RoleCatalog.model_validate(
                {
                    "roles": {
                        role_id: {
                            "faction": value.get("faction"),
                            "abilities": value.get("abilities", ()),
                        }
                        for role_id, value in roles.items()
                    }
                }
            ),
            abilities={
                ability_id: AbilityDefinition.model_validate(
                    {
                        key: value.get(key)
                        for key in (
                            "phase",
                            "action",
                            "validation_policy",
                            "resolution_policy",
                            "target_policy",
                            "start_day",
                        )
                    }
                )
                for ability_id, value in abilities.items()
            },
            phases=_phase_ids(composition),
            action_policy=_policy_id(composition, "action_policy", "standard"),
            resolution_policy=_policy_id(
                composition,
                "resolution_policy",
                "standard",
            ),
            phase_policy=_policy_id(composition, "phase_policy", "required_actions"),
            victory_policy=_policy_id(composition, "victory_policy", "faction_balance"),
            visibility_policy=_policy_id(composition, "visibility_policy", "standard"),
        )

    @classmethod
    def from_state(
        cls,
        state: GameState,
        composition: Mapping[str, object],
    ) -> RuleSetDefinition:
        """Rebuild a definition for one serialized aggregate state."""
        config = state.config
        return cls(
            player_count=config.player_count,
            role_counts=dict(config.role_counts),
            rules=config.rules,
            roles=config.roles,
            abilities=dict(config.abilities),
            phases=tuple(phase.value for phase in config.phase_order),
            action_policy=_policy_id(composition, "action_policy", "standard"),
            resolution_policy=_policy_id(
                composition,
                "resolution_policy",
                "standard",
            ),
            phase_policy=_policy_id(composition, "phase_policy", "required_actions"),
            victory_policy=_policy_id(composition, "victory_policy", "faction_balance"),
            visibility_policy=_policy_id(composition, "visibility_policy", "standard"),
        )


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


def _policy_id(
    composition: Mapping[str, object],
    key: str,
    default: str,
) -> str:
    return str(composition.get(key, default))


def _phase_ids(composition: Mapping[str, object]) -> tuple[str, ...]:
    value = composition.get("phases")
    if not isinstance(value, (list, tuple)):
        return ("night", "day_discussion", "voting")
    return tuple(str(phase) for phase in value)


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
        config_values = {
            "player_count": definition.player_count,
            "role_counts": definition.role_counts,
            "rules": definition.rules,
            "roles": definition.roles,
            "phase_order": tuple(Phase(phase) for phase in definition.phases),
        }
        config_values["abilities"] = definition.abilities
        config = GameConfig.model_validate(config_values)
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
