"""Setup-state helpers for Streamlit game creation screens."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any

from werewolf_agent.contracts.schemas import LocalRulesSettings, RoleDefinitionView, RulesetResponse
from werewolf_agent.interface.entrypoint.streamlit.i18n import I18nCatalog, Language

KEY_VIEW = "werewolf_streamlit_view"
KEY_SETUP_ROLE_COUNTS = "werewolf_streamlit_setup_role_counts"
KEY_SETUP_RULES = "werewolf_streamlit_setup_rules"
KEY_SETUP_PRESET = "werewolf_streamlit_setup_preset"
KEY_SETUP_SEED = "werewolf_streamlit_setup_seed"

VIEW_SETUP = "setup"
VIEW_OBSERVER_SETUP = "observer_setup"
VIEW_GAME = "game"
VIEW_SETTINGS = "settings"
VIEWS = frozenset({VIEW_SETUP, VIEW_OBSERVER_SETUP, VIEW_GAME, VIEW_SETTINGS})

PRESET_STANDARD = "standard"
PRESET_BEGINNER = "beginner"
PRESET_QUICK = "quick"
PRESET_LOGIC = "logic"
PRESETS = (PRESET_STANDARD, PRESET_BEGINNER, PRESET_QUICK, PRESET_LOGIC)


@dataclass(frozen=True)
class SetupValidation:
    """Validation result for one setup draft."""

    messages: list[str]

    @property
    def is_valid(self) -> bool:
        """Return whether the setup can create a game."""
        return not self.messages


def current_view(session: MutableMapping[str, Any]) -> str:
    """Return the selected Streamlit view."""
    view = str(session.get(KEY_VIEW, VIEW_SETUP))
    return view if view in VIEWS else VIEW_SETUP


def switch_view(session: MutableMapping[str, Any], view: str) -> None:
    """Switch the current Streamlit view."""
    session[KEY_VIEW] = view if view in VIEWS else VIEW_SETUP


def role_counts(session: MutableMapping[str, Any], ruleset: RulesetResponse) -> dict[str, int]:
    """Return role counts from session state or ruleset defaults."""
    raw_value = session.get(KEY_SETUP_ROLE_COUNTS)
    if not isinstance(raw_value, dict):
        return dict(ruleset.default_role_counts)
    counts = {
        role.id: max(0, int(raw_value.get(role.id, ruleset.default_role_counts.get(role.id, 0))))
        for role in ruleset.roles
    }
    return counts or dict(ruleset.default_role_counts)


def remember_role_counts(session: MutableMapping[str, Any], counts: Mapping[str, int]) -> None:
    """Store role counts in session state."""
    session[KEY_SETUP_ROLE_COUNTS] = {
        str(role_id): max(0, int(count)) for role_id, count in counts.items()
    }


def rules(session: MutableMapping[str, Any], ruleset: RulesetResponse) -> LocalRulesSettings:
    """Return active local rules from session state or ruleset defaults."""
    raw_value = session.get(KEY_SETUP_RULES)
    if not isinstance(raw_value, dict):
        return ruleset.default_rules
    return LocalRulesSettings.model_validate(raw_value)


def remember_rules(session: MutableMapping[str, Any], value: LocalRulesSettings) -> None:
    """Store active local rules in session state."""
    session[KEY_SETUP_RULES] = value.model_dump(mode="json")


def seed_text(session: MutableMapping[str, Any], default_seed: int) -> str:
    """Return the setup seed text."""
    return str(session.get(KEY_SETUP_SEED, default_seed))


def remember_seed_text(session: MutableMapping[str, Any], value: str) -> None:
    """Store the setup seed text."""
    session[KEY_SETUP_SEED] = value.strip()


def seed_from_text(value: str) -> int | None:
    """Return a parsed seed or None for an unfixed seed."""
    text = value.strip()
    return int(text) if text else None


def preset_counts(preset: str, ruleset: RulesetResponse) -> dict[str, int]:
    """Return role counts for a named preset."""
    if preset == PRESET_STANDARD:
        return dict(ruleset.default_role_counts)
    if preset == PRESET_BEGINNER:
        return _balanced_counts(ruleset, total=ruleset.player_count["min"], include_guard=False)
    if preset == PRESET_QUICK:
        return _balanced_counts(ruleset, total=ruleset.player_count["min"], include_guard=False)
    if preset == PRESET_LOGIC:
        return _balanced_counts(
            ruleset,
            total=sum(ruleset.default_role_counts.values()),
            include_guard=True,
        )
    return dict(ruleset.default_role_counts)


def validate_setup(
    counts: Mapping[str, int],
    ruleset: RulesetResponse,
    *,
    catalog: I18nCatalog,
    lang: Language,
) -> SetupValidation:
    """Validate role counts for the setup screen."""
    messages: list[str] = []
    total = sum(counts.values())
    min_players = ruleset.player_count["min"]
    max_players = ruleset.player_count["max"]
    if total < min_players or total > max_players:
        messages.append(catalog.t(lang, "setup.validation.total", min=min_players, max=max_players))

    known_role_ids = {role.id for role in ruleset.roles}
    unknown_roles = sorted(set(counts) - known_role_ids)
    if unknown_roles:
        messages.append(
            catalog.t(lang, "setup.validation.unknown_roles", roles=", ".join(unknown_roles))
        )

    if any(count < 0 for count in counts.values()):
        messages.append(catalog.t(lang, "setup.validation.negative"))

    if _faction_count(counts, ruleset.roles, "werewolf") < 1:
        messages.append(catalog.t(lang, "setup.validation.faction.werewolf"))
    if _faction_count(counts, ruleset.roles, "village") < 1:
        messages.append(catalog.t(lang, "setup.validation.faction.village"))
    return SetupValidation(messages=messages)


def seat_options(counts: Mapping[str, int]) -> list[tuple[str, str]]:
    """Return generated human seat options."""
    total = sum(counts.values())
    return [(f"player-{index}", f"P{index}") for index in range(1, total + 1)]


def setup_summary(
    counts: Mapping[str, int],
    *,
    rules: LocalRulesSettings,
    ruleset: RulesetResponse,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    """Return a compact setup summary."""
    role_parts = [
        f"{catalog.label(lang, 'role', role_id)} {count}"
        for role_id, count in counts.items()
        if count > 0
    ]
    tie_rule = catalog.t(
        lang,
        "setup.summary.tie.no_elimination"
        if rules.enable_no_elimination_on_tie
        else "setup.summary.tie.random_elimination",
    )
    first_night = catalog.t(
        lang,
        "setup.summary.first_night.on"
        if rules.enable_first_night_attack
        else "setup.summary.first_night.off",
    )
    return catalog.t(
        lang,
        "setup.summary",
        players=sum(counts.values()),
        roles=", ".join(role_parts),
        first_night=first_night,
        tie_rule=tie_rule,
    )


def _balanced_counts(
    ruleset: RulesetResponse,
    *,
    total: int,
    include_guard: bool,
) -> dict[str, int]:
    counts = {role.id: 0 for role in ruleset.roles}
    werewolf = _first_role(ruleset.roles, faction="werewolf")
    village = _first_role(ruleset.roles, faction="village", without_abilities=True) or _first_role(
        ruleset.roles,
        faction="village",
    )
    inspector = _first_role(ruleset.roles, ability="inspect")
    guard = _first_role(ruleset.roles, ability="guard") if include_guard else None
    for role in (werewolf, inspector, guard):
        if role is not None:
            counts[role.id] += 1
    filled = sum(counts.values())
    if village is not None and filled < total:
        counts[village.id] += total - filled
    return counts


def _first_role(
    roles: list[RoleDefinitionView],
    *,
    faction: str | None = None,
    ability: str | None = None,
    without_abilities: bool = False,
) -> RoleDefinitionView | None:
    for role in roles:
        if faction is not None and role.faction != faction:
            continue
        if ability is not None and ability not in role.abilities:
            continue
        if without_abilities and role.abilities:
            continue
        return role
    return None


def _faction_count(
    counts: Mapping[str, int],
    roles: list[RoleDefinitionView],
    faction: str,
) -> int:
    role_factions = {role.id: role.faction for role in roles}
    return sum(count for role_id, count in counts.items() if role_factions.get(role_id) == faction)
