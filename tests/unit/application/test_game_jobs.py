import inspect
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

import werewolf_agent.application as application_api
import werewolf_agent.application.handlers as usecases
from werewolf_agent.adapters.llm.configuration import LlmProviderConfig
from werewolf_agent.adapters.resources import (
    LlmDefinitions,
)
from werewolf_agent.agents.definitions import (
    FakeDecisionCatalog,
    PromptDefinition,
    PromptMessageDefinition,
)
from werewolf_agent.application import Actor, GameApplication
from werewolf_agent.application.definitions import (
    AbilityDefinition,
    GameCatalogDefinitions,
    GameDefinitions,
    GameRoleDefinitions,
    GameRuleDefinitions,
    LocalRulesDefinition,
    NarrationProfileDefinition,
    PlayerProfile,
    PlayerRoster,
    PlayerSetupDefinitions,
    RoleDefinition,
    ScenarioDefinition,
    SetupPresetDefinition,
)
from werewolf_agent.application.models import (
    AdvanceGameCommand,
    ApplicationContext,
    CreateGameCommand,
    GameApplicationConfig,
    GameEventCreate,
    GameRecordCreate,
    GameRecordUpdate,
    GetGameQuery,
    GetGameRevealQuery,
    GetPlayerObservationQuery,
    ListGamesQuery,
    ListTimelineQuery,
    PlayerActionCommand,
    StoredGame,
    StoredGameEvent,
    StoredGameSummary,
    StoredGameTurn,
)
from werewolf_agent.application.ports import GameRepository
from werewolf_agent.contracts import (
    GameError,
    GameNotFoundError,
    GameStatus,
    InvalidGameIdError,
)
from werewolf_agent.settings.constants import MAX_GAME_LIST_LIMIT, MAX_TIMELINE_LIMIT
from werewolf_agent.settings.defaults import PACKAGED_DEFAULTS

NOW = datetime(2026, 1, 1, tzinfo=UTC)
DEFAULT_ROLE_COUNTS = {"werewolf": 1, "seer": 1, "knight": 1, "villager": 2}
DEFAULT_AGENT_TYPE = "llm"


class UsecaseHarness:
    """Test helper that binds a context outside the stateless usecase package."""

    def __init__(self, context: ApplicationContext) -> None:
        self.context = context

    def __getattr__(self, name: str):
        if name == "advance_game":
            from werewolf_agent.adapters.agents.game_driver import AgentRuntime, advance_game

            runtime = AgentRuntime(
                config=_llm_provider_config(),
                definitions=llm_definitions(),
            )
            return lambda value: advance_game(self.context, value, runtime=runtime)
        operation = getattr(usecases, name)
        return lambda value: operation(value, dependencies=self.context)

    @staticmethod
    def get_setup_options(config, game_definitions, llm_definitions):
        from werewolf_agent.application.setup_options import default_setup_options

        return default_setup_options(config, game_definitions, llm_definitions)


def test_dependencies_require_definition_values() -> None:
    with pytest.raises(TypeError):
        ApplicationContext(repository=object())  # type: ignore[arg-type,call-arg]


def test_actor_requires_a_non_blank_external_subject() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        Actor(user_id="  ")


def test_game_application_accepts_only_public_creation_and_page_inputs() -> None:
    deps, _repository = dependencies()
    games = GameApplication(deps)
    actor = Actor(user_id="user-1")

    created = games.create(create_command(seed=1))
    page = games.list(actor, limit=10, offset=0)

    assert page.games[0]["game_id"] == created.game_id
    assert _repository.last_list_user_id == actor.user_id
    assert "llm_mode" not in inspect.signature(GameApplication.create).parameters


def test_create_command_can_be_built_from_the_application_public_surface() -> None:
    rules = local_rules_definition()
    command = application_api.CreateGameCommand(
        narration_mode="none",
        role_counts=DEFAULT_ROLE_COUNTS,
        rules=application_api.LocalRulesDefinition(**rules.model_dump()),
    )

    assert command.player_count == 5


def test_game_application_owns_game_and_player_authorization() -> None:
    class DenyAccess:
        def require_game_access(self, game_id: str, *, user_id: str) -> None:
            raise PermissionError(f"{user_id}:{game_id}")

        def require_player_access(self, game_id: str, player_id: str, *, user_id: str) -> None:
            raise PermissionError(f"{user_id}:{game_id}:{player_id}")

    deps, _repository = dependencies()
    games = GameApplication(deps, access_policy=DenyAccess())
    actor = Actor(user_id="user-1")

    with pytest.raises(PermissionError):
        games.get(str(uuid4()), actor)
    with pytest.raises(PermissionError):
        games.observation(str(uuid4()), actor, "player-1")
    with pytest.raises(PermissionError):
        games.commit_advance(
            actor,
            SimpleNamespace(game_id=str(uuid4())),  # type: ignore[arg-type]
        )


def test_game_application_uses_only_the_dependency_selected_llm_mode() -> None:
    deps, repository = dependencies()
    trusted_deps = ApplicationContext(
        repository=deps.repository,
        game_definitions=deps.game_definitions,
        player_definitions=deps.player_definitions,
        config=deps.config,
        create_llm_mode="paid",
    )

    created = GameApplication(trusted_deps).create(create_command(seed=1))

    assert repository.games[UUID(created.game_id)].config["llm_mode"] == "paid"


def test_create_game_materializes_an_omitted_seed_for_replay() -> None:
    deps, repository = dependencies()

    created = GameApplication(deps).create(create_command(seed=None))
    stored = repository.games[UUID(created.game_id)]

    assert isinstance(created.state["seed"], int)
    assert stored.seed == created.state["seed"]


class InMemoryGameRepository(GameRepository):
    def __init__(self) -> None:
        self.games: dict[UUID, StoredGame] = {}
        self.events: dict[UUID, list[StoredGameEvent]] = {}
        self.turns: dict[UUID, list[StoredGameTurn]] = {}
        self.last_list_user_id: str | None = None

    def create(self, game: GameRecordCreate) -> StoredGame:
        stored = StoredGame(
            id=game.id,
            status=game.status,
            phase=game.phase,
            day=game.day,
            seed=game.seed,
            config=game.config,
            public_state=game.public_state,
            private_state=game.private_state,
            pending_actions=game.pending_actions,
            version=game.version,
            created_at=NOW,
            updated_at=NOW,
        )
        self.games[stored.id] = stored
        self.events[stored.id] = []
        self.turns[stored.id] = []
        return stored

    def get(self, game_id: UUID) -> StoredGame | None:
        return self.games.get(game_id)

    def get_for_update(self, game_id: UUID) -> StoredGame | None:
        return self.get(game_id)

    def list_game_summaries(
        self,
        *,
        user_id: str,
        status: GameStatus | None,
        limit: int,
        offset: int,
    ) -> list[StoredGameSummary]:
        self.last_list_user_id = user_id
        games = [
            game
            for game in sorted(self.games.values(), key=lambda item: item.created_at, reverse=True)
            if status is None or game.status == status
        ]
        return [self._summary(game) for game in games[offset : offset + limit]]

    def save(self, update: GameRecordUpdate) -> StoredGame:
        current = self.games[update.id]
        stored = StoredGame(
            id=update.id,
            status=update.status,
            phase=update.phase,
            day=update.day,
            seed=current.seed,
            config=current.config,
            public_state=update.public_state,
            private_state=update.private_state,
            pending_actions=update.pending_actions,
            version=update.version,
            created_at=current.created_at,
            updated_at=NOW,
        )
        self.games[stored.id] = stored
        return stored

    def append_events(
        self,
        game_id: UUID,
        events: Sequence[GameEventCreate],
    ) -> list[StoredGameEvent]:
        stream = self.events.setdefault(game_id, [])
        records = [
            StoredGameEvent(
                sequence=len(stream) + offset,
                event_id=uuid4(),
                visibility=event.visibility,
                phase=event.phase,
                day=event.day,
                actor_id=event.actor_id,
                event_type=event.event_type,
                payload=event.payload,
                occurred_at=NOW,
            )
            for offset, event in enumerate(events, start=1)
        ]
        stream.extend(records)
        turn_stream = self.turns.setdefault(game_id, [])
        game = self.games[game_id]
        turn_stream.extend(
            StoredGameTurn(
                sequence=len(turn_stream) + offset,
                event_sequence=event.sequence,
                version=game.version,
                phase=event.phase,
                day=event.day,
                actor_id=event.actor_id,
                event_type=event.event_type,
                payload=event.payload,
                occurred_at=event.occurred_at,
            )
            for offset, event in enumerate(records, start=1)
            if event.visibility == "public"
        )
        return records

    def latest_public_turn_sequence(self, game_id: UUID) -> int:
        turns = self.turns.get(game_id, [])
        return turns[-1].sequence if turns else 0

    def list_public_turns(
        self,
        game_id: UUID,
        *,
        after: int,
        limit: int,
    ) -> list[StoredGameTurn]:
        return [turn for turn in self.turns.get(game_id, []) if turn.sequence > after][:limit]

    def _summary(self, game: StoredGame) -> StoredGameSummary:
        state = game.public_state
        summary = state.get("summary") or {}
        return StoredGameSummary(
            game_id=game.id,
            status=game.status,
            phase=game.phase,
            day=game.day,
            version=game.version,
            seed=game.seed,
            player_count=len(state.get("players") or []),
            alive_count=int(summary.get("alive_count") or 0),
            winner=state.get("winner"),
            step_count=max(game.version - 1, 0),
            turn_count=len(self.turns.get(game.id, [])),
            created_at=game.created_at,
            updated_at=game.updated_at,
            completed_at=game.updated_at if game.status == "completed" else None,
        )


def dependencies(
    *,
    config: GameApplicationConfig | None = None,
) -> tuple[ApplicationContext, InMemoryGameRepository]:
    repository = InMemoryGameRepository()
    return ApplicationContext(
        repository=repository,
        game_definitions=game_definitions(),
        player_definitions=player_definitions(),
        config=config or application_config(),
    ), repository


def _llm_provider_config() -> LlmProviderConfig:
    return LlmProviderConfig(
        provider="fake",
        model="fake-list-llm",
        base_url="",
        api_key="",
        timeout_seconds=30.0,
        max_retries=2,
        max_tokens=96,
        temperature=0.7,
        structured_output_mode="auto",
        validation_retry_count=1,
        graph_max_steps=16,
        fallback_policy="deterministic_legal_action",
    )


def application_config(
    *,
    min_players: int = 5,
    max_players: int = 8,
    default_player_count: int = 5,
    supported_agent_type: str = DEFAULT_AGENT_TYPE,
    default_setup_preset_id: str = "standard_5",
) -> GameApplicationConfig:
    return GameApplicationConfig(
        min_players=min_players,
        max_players=max_players,
        default_player_count=default_player_count,
        supported_agent_type=supported_agent_type,
        default_setup_preset_id=default_setup_preset_id,
        default_narration_mode=str(PACKAGED_DEFAULTS["game_default_narration_mode"]),
        game_list_default_limit=int(PACKAGED_DEFAULTS["api_game_list_default_limit"]),
        game_list_max_limit=MAX_GAME_LIST_LIMIT,
        timeline_default_limit=int(PACKAGED_DEFAULTS["api_timeline_default_limit"]),
        timeline_max_limit=MAX_TIMELINE_LIMIT,
    )


def local_rules_definition() -> LocalRulesDefinition:
    return LocalRulesDefinition(
        day_speech_limit_per_player=1,
        allow_self_vote=False,
        allow_vote_revision=False,
        allow_night_action_revision=False,
        enable_first_night_attack=True,
        enable_no_elimination_on_tie=True,
        enable_random_elimination_on_tie=False,
        allow_knight_self_guard=True,
        allow_knight_repeat_guard=True,
        allow_seer_self_inspect=False,
        allow_werewolf_friendly_fire=False,
        reveal_role_on_death=False,
    )


def game_definitions() -> GameDefinitions:
    return GameDefinitions(
        rules=GameRuleDefinitions(local_rules=local_rules_definition()),
        roles=GameRoleDefinitions(
            roles={
                "villager": RoleDefinition(faction="village", abilities=()),
                "werewolf": RoleDefinition(
                    faction="werewolf",
                    abilities=("night_attack", "pack_knowledge"),
                ),
                "seer": RoleDefinition(faction="village", abilities=("inspect",)),
                "knight": RoleDefinition(faction="village", abilities=("guard",)),
            },
            default_role_counts={5: DEFAULT_ROLE_COUNTS},
        ),
        catalog=GameCatalogDefinitions(
            abilities={
                "night_attack": AbilityDefinition(
                    phase="night",
                    action="werewolf_attack",
                    validation_policy="standard",
                    resolution_policy="standard",
                    target_policy="other_alive_non_pack",
                    start_day=1,
                    label="Attack",
                    description="Attack one player.",
                ),
                "pack_knowledge": AbilityDefinition(
                    phase="night",
                    action="pass",
                    validation_policy="standard",
                    resolution_policy="standard",
                    target_policy="none",
                    start_day=1,
                    label="Pack knowledge",
                    description="Know allied players.",
                ),
                "inspect": AbilityDefinition(
                    phase="night",
                    action="seer_inspect",
                    validation_policy="standard",
                    resolution_policy="standard",
                    target_policy="other_alive",
                    start_day=1,
                    label="Inspect",
                    description="Inspect one player.",
                ),
                "guard": AbilityDefinition(
                    phase="night",
                    action="knight_guard",
                    validation_policy="standard",
                    resolution_policy="standard",
                    target_policy="alive",
                    start_day=1,
                    label="Guard",
                    description="Guard one player.",
                ),
            },
            scenarios={
                "classic": ScenarioDefinition(
                    label="Classic",
                    summary="Classic game.",
                    prompt_premise="A village debates.",
                    narration_profile="standard",
                    recommended_setup_preset="standard_5",
                )
            },
            narration_profiles={"standard": NarrationProfileDefinition()},
            setup_presets={
                "standard_5": SetupPresetDefinition(
                    label="Standard 5",
                    scenario_id="classic",
                    role_counts=DEFAULT_ROLE_COUNTS,
                )
            },
        ),
    )


def llm_definitions() -> LlmDefinitions:
    return LlmDefinitions(
        players=PlayerRoster(
            players={
                "default": PlayerProfile(
                    name="葵",
                    age=26,
                    gender="指定なし",
                    personality="Careful",
                    speaking_style="Short",
                    reasoning_style="Logical",
                    risk_tolerance="medium",
                ),
                "sharp": PlayerProfile(
                    name="蓮",
                    age=31,
                    gender="男性",
                    personality="Sharp",
                    speaking_style="Direct",
                    reasoning_style="Contradiction first",
                    risk_tolerance="high",
                ),
                "quiet": PlayerProfile(
                    name="遥",
                    age=28,
                    gender="女性",
                    personality="Quiet",
                    speaking_style="Calm",
                    reasoning_style="Evidence first",
                    risk_tolerance="low",
                ),
                "steady": PlayerProfile(
                    name="湊",
                    age=34,
                    gender="男性",
                    personality="Steady",
                    speaking_style="Brief",
                    reasoning_style="Vote first",
                    risk_tolerance="medium",
                ),
                "curious": PlayerProfile(
                    name="芽衣",
                    age=27,
                    gender="女性",
                    personality="Curious",
                    speaking_style="Questioning",
                    reasoning_style="Ask for reasons",
                    risk_tolerance="medium",
                ),
            }
        ),
        prompt=PromptDefinition(
            name="test",
            version=1,
            alias="local",
            input_variables=[
                "player_id",
                "phase",
                "day",
                "role",
                "scenario_name",
                "scenario_premise",
                "character_profile",
                "available_actions",
                "selected_action",
                "role_hint",
                "target_rankings_json",
                "legal_targets_json",
                "observation_json",
                "format_instructions",
            ],
            response_format={"schema": "AgentDecision"},
            messages=[
                PromptMessageDefinition(
                    role="human",
                    content=(
                        "{{player_id}} {{phase}} {{day}} {{role}} "
                        "{{scenario_name}} {{scenario_premise}} {{character_profile}} "
                        "{{available_actions}} {{selected_action}} {{role_hint}} "
                        "{{target_rankings_json}} {{legal_targets_json}} "
                        "{{observation_json}} {{format_instructions}}"
                    ),
                )
            ],
        ),
        fake_responses=FakeDecisionCatalog(
            name="test",
            version=1,
            alias="local",
            templates={
                "speech": (
                    '{"type":"speech","player_id":"$player_id","message":"hello from $player_name"}'
                ),
                "vote": ('{"type":"vote","player_id":"$player_id","target_id":"$target_id"}'),
                "werewolf_attack": (
                    '{"type":"werewolf_attack","player_id":"$player_id","target_id":"$target_id"}'
                ),
                "seer_inspect": (
                    '{"type":"seer_inspect","player_id":"$player_id","target_id":"$target_id"}'
                ),
                "knight_guard": (
                    '{"type":"knight_guard","player_id":"$player_id","target_id":"$target_id"}'
                ),
                "pass": '{"type":"pass","player_id":"$player_id","reason":"fallback"}',
            },
        ),
    )


def player_definitions() -> PlayerSetupDefinitions:
    return PlayerSetupDefinitions(players=llm_definitions().players)


def create_command(**values: object) -> CreateGameCommand:
    values.setdefault("role_counts", DEFAULT_ROLE_COUNTS)
    values.setdefault("rules", local_rules_definition())
    values.setdefault("narration_mode", PACKAGED_DEFAULTS["game_default_narration_mode"])
    return CreateGameCommand.model_validate(values)


def _first_target(observation: dict[str, object], *, player_id: str) -> str:
    known_roles = observation.get("known_roles")
    known_wolves = set()
    if isinstance(known_roles, dict):
        known_wolves = {
            str(target_id) for target_id, role in known_roles.items() if role == "werewolf"
        }
    players = observation.get("players")
    assert isinstance(players, list)
    for player in players:
        assert isinstance(player, dict)
        if (
            player.get("id") != player_id
            and player.get("status") == "alive"
            and player.get("id") not in known_wolves
        ):
            return str(player["id"])
    raise AssertionError("no target candidate")


def _advance_until_manual_input(
    use_cases: UsecaseHarness,
    game_id: str,
    *,
    max_steps: int = 8,
) -> None:
    for _ in range(max_steps):
        try:
            use_cases.advance_game(AdvanceGameCommand(game_id=game_id))
        except GameError:
            return
    raise AssertionError("manual input was not required")


def test_default_setup_options_returns_business_identifiers_only() -> None:
    deps, _repository = dependencies(
        config=application_config(
            min_players=4,
            max_players=10,
            default_player_count=5,
            supported_agent_type=DEFAULT_AGENT_TYPE,
            default_setup_preset_id="standard_5",
        )
    )
    result = UsecaseHarness.get_setup_options(
        deps.config,
        deps.game_definitions,
        deps.player_definitions,
    )

    assert result.player_count == {"min": 4, "max": 10}
    assert set(result.roles) == {"villager", "werewolf", "seer", "knight"}
    assert result.default_role_counts == DEFAULT_ROLE_COUNTS
    assert result.default_rules == local_rules_definition()
    assert result.default_setup_preset_id == "standard_5"
    assert result.default_scenario_id == "classic"


def test_default_setup_options_rejects_an_unknown_configured_preset() -> None:
    with pytest.raises(ValueError, match="Unknown setup preset: missing"):
        UsecaseHarness.get_setup_options(
            application_config(default_setup_preset_id="missing"),
            game_definitions(),
            player_definitions(),
        )


def test_create_game_generates_player_ids_and_sanitizes_public_events() -> None:
    deps, repository = dependencies()

    result = UsecaseHarness(deps).create_game(create_command(seed=42))

    assert [player["id"] for player in result.state["players"]] == [
        "player-1",
        "player-2",
        "player-3",
        "player-4",
        "player-5",
    ]
    assert "role" not in json.dumps(result.model_dump(mode="json"))
    event_stream = repository.events[UUID(result.game_id)]
    assert event_stream[0].event_type == "game_started"
    assert "role_counts" not in event_stream[0].payload


def test_create_game_selects_seeded_roster_names_for_default_players() -> None:
    deps, _repository = dependencies()
    use_cases = UsecaseHarness(deps)

    first = use_cases.create_game(create_command(seed=10))
    second = use_cases.create_game(create_command(seed=10))
    third = use_cases.create_game(create_command(seed=11))

    first_names = [player["name"] for player in first.state["players"]]
    second_names = [player["name"] for player in second.state["players"]]
    third_names = [player["name"] for player in third.state["players"]]

    assert first_names == second_names
    assert first_names != third_names
    assert len(set(first_names)) == 5
    assert not any(str(name).startswith("Player ") for name in first_names)


def test_create_game_marks_requested_manual_seat_without_public_credential() -> None:
    deps, repository = dependencies()

    result = UsecaseHarness(deps).create_game(
        create_command(manual_player_id="player-1", seed=42),
    )
    stored = repository.get(UUID(result.game_id))

    assert stored is not None
    assert stored.config["player_agent_types"]["player-1"] == "manual"


def test_reveal_returns_roles_and_private_resolution_without_changing_public_state() -> None:
    deps, _repository = dependencies()
    use_cases = UsecaseHarness(deps)
    created = use_cases.create_game(create_command(seed=1))
    use_cases.advance_game(AdvanceGameCommand(game_id=created.game_id))

    reveal = use_cases.get_game_reveal(GetGameRevealQuery(game_id=created.game_id))
    public_state = use_cases.get_game(GetGameQuery(game_id=created.game_id))

    assert reveal.role_counts == DEFAULT_ROLE_COUNTS
    assert {player.role for player in reveal.players} >= {"werewolf", "villager"}
    assert reveal.nights
    assert "role" in json.dumps(reveal.model_dump(mode="json"))
    assert "role" not in json.dumps(public_state.model_dump(mode="json"))


def test_create_game_rejects_out_of_range_role_count_total() -> None:
    deps, _repository = dependencies()

    with pytest.raises(GameError):
        UsecaseHarness(deps).create_game(create_command(role_counts={"werewolf": 1, "villager": 3}))


def test_game_id_is_parsed_and_validated_inside_usecase() -> None:
    deps, _repository = dependencies()

    with pytest.raises(InvalidGameIdError):
        UsecaseHarness(deps).get_game(GetGameQuery(game_id="not-a-uuid"))

    with pytest.raises(GameNotFoundError):
        UsecaseHarness(deps).get_game(GetGameQuery(game_id=str(uuid4())))


def test_advance_game_delegates_core_progression_and_returns_public_payloads() -> None:
    deps, repository = dependencies()
    use_cases = UsecaseHarness(deps)
    created = use_cases.create_game(create_command(seed=1))

    advanced = use_cases.advance_game(AdvanceGameCommand(game_id=created.game_id))
    timeline = use_cases.list_timeline(ListTimelineQuery(game_id=created.game_id, after=0))

    assert advanced.state["version"] == 2
    assert advanced.timeline
    assert "role_counts" not in json.dumps(timeline.model_dump(mode="json"))
    assert "attacked_player_id" not in json.dumps(timeline.model_dump(mode="json"))
    assert "protected_player_id" not in json.dumps(timeline.model_dump(mode="json"))
    assert timeline.items
    assert any(
        item["event_type"] == "night_resolved" and set(item["payload"]) <= {"killed_player_id"}
        for item in timeline.model_dump(mode="json")["items"]
    )
    assert timeline.next_after <= repository.latest_public_turn_sequence(UUID(created.game_id))


def test_fake_list_llm_can_complete_a_game() -> None:
    deps, _repository = dependencies()
    use_cases = UsecaseHarness(deps)
    game = use_cases.create_game(create_command(seed=1))

    for _ in range(30):
        if game.state["status"] == "completed":
            break
        game = use_cases.advance_game(AdvanceGameCommand(game_id=game.game_id))

    assert game.state["status"] == "completed"
    assert game.state["winner"] in {"village", "werewolf"}


def test_death_role_reveal_is_applied_only_to_dead_players_when_enabled() -> None:
    deps, _repository = dependencies()
    use_cases = UsecaseHarness(deps)
    rules = local_rules_definition().model_copy(update={"reveal_role_on_death": True})
    game = use_cases.create_game(create_command(seed=1, rules=rules))

    for _ in range(30):
        dead = [player for player in game.state["players"] if not player["alive"]]
        if dead:
            break
        game = use_cases.advance_game(AdvanceGameCommand(game_id=game.game_id))

    dead = [player for player in game.state["players"] if not player["alive"]]
    alive = [player for player in game.state["players"] if player["alive"]]
    assert dead
    assert all(player["role"] and player["faction"] for player in dead)
    assert all("role" not in player and "faction" not in player for player in alive)


def test_discussion_timeline_contains_fake_speeches_without_private_fields() -> None:
    deps, _repository = dependencies()
    use_cases = UsecaseHarness(deps)
    created = use_cases.create_game(create_command(seed=1))

    use_cases.advance_game(AdvanceGameCommand(game_id=created.game_id))
    advanced = use_cases.advance_game(AdvanceGameCommand(game_id=created.game_id))
    serialized = json.dumps(advanced.timeline)
    speech_events = [item for item in advanced.timeline if item["event_type"] == "speech_recorded"]

    assert speech_events
    assert all(item["payload"]["message"] for item in speech_events)
    assert "role_counts" not in serialized
    assert "target_role" not in serialized
    assert "target_faction" not in serialized


def test_submit_manual_action_returns_public_safe_result() -> None:
    deps, repository = dependencies()
    use_cases = UsecaseHarness(deps)
    created = use_cases.create_game(
        create_command(manual_player_id="player-1", seed=2),
    )
    _advance_until_manual_input(use_cases, created.game_id)
    observation = use_cases.get_player_observation(
        GetPlayerObservationQuery(
            game_id=created.game_id,
            player_id="player-1",
            trusted_user_id="user-1",
        )
    )
    action_type = str(observation.observation["available_actions"][0])
    target_id = None
    message = None
    if action_type == "speech":
        message = "hello"
    else:
        target_id = _first_target(observation.observation, player_id="player-1")
    version_before_action = repository.games[UUID(created.game_id)].version

    result = use_cases.submit_player_action(
        PlayerActionCommand(
            game_id=created.game_id,
            player_id="player-1",
            trusted_user_id="user-1",
            type=action_type,
            target_id=target_id,
            message=message,
        )
    )

    serialized = result.model_dump_json()
    assert "seat_credential" not in serialized
    assert "trusted_user_id" not in serialized
    assert result.state["version"] == version_before_action + 1


def test_manual_input_blocks_advance_and_duplicate_actions() -> None:
    deps, _repository = dependencies()
    use_cases = UsecaseHarness(deps)
    created = use_cases.create_game(
        create_command(manual_player_id="player-1", seed=2),
    )

    _advance_until_manual_input(use_cases, created.game_id)
    with pytest.raises(GameError):
        use_cases.advance_game(AdvanceGameCommand(game_id=created.game_id))

    observation = use_cases.get_player_observation(
        GetPlayerObservationQuery(
            game_id=created.game_id,
            player_id="player-1",
            trusted_user_id="user-1",
        )
    )
    action_type = str(observation.observation["available_actions"][0])
    target_id = None
    if action_type != "speech":
        target_id = _first_target(observation.observation, player_id="player-1")
    command = PlayerActionCommand(
        game_id=created.game_id,
        player_id="player-1",
        trusted_user_id="user-1",
        type=action_type,
        target_id=target_id,
        message="hello" if action_type == "speech" else None,
    )

    use_cases.submit_player_action(command)
    with pytest.raises(GameError):
        use_cases.submit_player_action(command)


def test_list_games_and_turns_return_public_read_models() -> None:
    deps, _repository = dependencies()
    use_cases = UsecaseHarness(deps)
    created = use_cases.create_game(create_command(seed=1))
    use_cases.advance_game(AdvanceGameCommand(game_id=created.game_id))

    games = use_cases.list_games(ListGamesQuery(trusted_user_id="user-1", limit=10))
    timeline = use_cases.list_timeline(ListTimelineQuery(game_id=created.game_id))

    assert games.games[0]["game_id"] == created.game_id
    assert games.games[0]["turn_count"] == len(timeline.items)
    assert timeline.items
    assert "role_counts" not in json.dumps(timeline.model_dump(mode="json"))
