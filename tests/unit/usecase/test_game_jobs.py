import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from werewolf_agent.commons.shared.definitions import (
    FakeDecisionCatalog,
    GameDefinitions,
    GameRoleDefinitions,
    GameRuleDefinitions,
    LlmDefinitions,
    LocalRulesDefinition,
    PlayerProfile,
    PlayerRoster,
    PromptDefinition,
    PromptMessageDefinition,
    RoleDefinition,
)
from werewolf_agent.contracts import GameError, GameNotFoundError, InvalidGameIdError
from werewolf_agent.usecase.jobs import (
    AdvanceGameRunCommand,
    AdvanceUntilInputCommand,
    CreateGameCommand,
    GameEventCreate,
    GameRepository,
    GameRunCreate,
    GameRunUpdate,
    GameStatus,
    GameUseCaseConfig,
    GameUseCaseDependencies,
    GameUseCases,
    GetGameRevealQuery,
    GetGameRunQuery,
    GetGameTimelineQuery,
    GetPlayerObservationQuery,
    ListGameRunsQuery,
    LlmProviderConfig,
    PlayerActionCommand,
    StoredGameEvent,
    StoredGameRun,
    StoredGameRunSummary,
    StoredGameTurn,
    TelemetryEvent,
    TelemetrySink,
)
from werewolf_agent.usecase.jobs.telemetry import NullTelemetrySink

NOW = datetime(2026, 1, 1, tzinfo=UTC)
DEFAULT_ROLE_COUNTS = {"werewolf": 1, "seer": 1, "knight": 1, "villager": 2}
DEFAULT_AGENT_TYPE = "llm"


def test_null_telemetry_sink_accepts_events() -> None:
    NullTelemetrySink().record(TelemetryEvent("game.phase.advance_started"))


def test_dependencies_require_definition_values() -> None:
    with pytest.raises(TypeError):
        GameUseCaseDependencies(repository=object())  # type: ignore[arg-type,call-arg]


class InMemoryGameRepository(GameRepository):
    def __init__(self) -> None:
        self.runs: dict[UUID, StoredGameRun] = {}
        self.events: dict[UUID, list[StoredGameEvent]] = {}
        self.turns: dict[UUID, list[StoredGameTurn]] = {}

    def create(self, run: GameRunCreate) -> StoredGameRun:
        stored = StoredGameRun(
            id=run.id,
            status=run.status,
            phase=run.phase,
            day=run.day,
            seed=run.seed,
            config=run.config,
            public_state=run.public_state,
            private_state=run.private_state,
            pending_actions=run.pending_actions,
            control_token_hashes=run.control_token_hashes,
            version=run.version,
            created_at=NOW,
            updated_at=NOW,
        )
        self.runs[stored.id] = stored
        self.events[stored.id] = []
        self.turns[stored.id] = []
        return stored

    def get(self, game_id: UUID) -> StoredGameRun | None:
        return self.runs.get(game_id)

    def get_for_update(self, game_id: UUID) -> StoredGameRun | None:
        return self.get(game_id)

    def list_run_summaries(
        self,
        *,
        status: GameStatus | None,
        limit: int,
        offset: int,
    ) -> list[StoredGameRunSummary]:
        runs = [
            run
            for run in sorted(self.runs.values(), key=lambda item: item.created_at, reverse=True)
            if status is None or run.status == status
        ]
        return [self._summary(run) for run in runs[offset : offset + limit]]

    def save(self, update: GameRunUpdate) -> StoredGameRun:
        current = self.runs[update.id]
        stored = StoredGameRun(
            id=update.id,
            status=update.status,
            phase=update.phase,
            day=update.day,
            seed=current.seed,
            config=current.config,
            public_state=update.public_state,
            private_state=update.private_state,
            pending_actions=update.pending_actions,
            control_token_hashes=current.control_token_hashes,
            version=update.version,
            created_at=current.created_at,
            updated_at=NOW,
        )
        self.runs[stored.id] = stored
        return stored

    def append_events(
        self,
        run_id: UUID,
        events: Sequence[GameEventCreate],
    ) -> list[StoredGameEvent]:
        stream = self.events.setdefault(run_id, [])
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
        turn_stream = self.turns.setdefault(run_id, [])
        run = self.runs[run_id]
        turn_stream.extend(
            StoredGameTurn(
                sequence=len(turn_stream) + offset,
                event_sequence=event.sequence,
                version=run.version,
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

    def latest_public_turn_sequence(self, run_id: UUID) -> int:
        turns = self.turns.get(run_id, [])
        return turns[-1].sequence if turns else 0

    def list_public_turns(
        self,
        run_id: UUID,
        *,
        after: int,
        limit: int,
    ) -> list[StoredGameTurn]:
        return [turn for turn in self.turns.get(run_id, []) if turn.sequence > after][:limit]

    def _summary(self, run: StoredGameRun) -> StoredGameRunSummary:
        state = run.public_state
        summary = state.get("summary") or {}
        return StoredGameRunSummary(
            game_id=run.id,
            status=run.status,
            phase=run.phase,
            day=run.day,
            version=run.version,
            seed=run.seed,
            player_count=len(state.get("players") or []),
            alive_count=int(summary.get("alive_count") or 0),
            winner=state.get("winner"),
            step_count=max(run.version - 1, 0),
            turn_count=len(self.turns.get(run.id, [])),
            created_at=run.created_at,
            updated_at=run.updated_at,
            completed_at=run.updated_at if run.status == "completed" else None,
        )


class CollectingTelemetrySink:
    def __init__(self) -> None:
        self.events: list[TelemetryEvent] = []

    def record(self, event: TelemetryEvent) -> None:
        self.events.append(event)


def dependencies(
    *,
    config: GameUseCaseConfig | None = None,
    telemetry: TelemetrySink | None = None,
) -> tuple[GameUseCaseDependencies, InMemoryGameRepository]:
    repository = InMemoryGameRepository()
    return GameUseCaseDependencies(
        repository=repository,
        game_definitions=game_definitions(),
        llm_definitions=llm_definitions(),
        config=config or usecase_config(),
        llm_provider_config=LlmProviderConfig(
            provider="fake",
            model="fake-list-llm",
            base_url="",
            api_key="",
            timeout_seconds=30.0,
            max_retries=2,
            temperature=0.7,
        ),
        telemetry=telemetry or CollectingTelemetrySink(),
    ), repository


def usecase_config(
    *,
    min_players: int = 5,
    max_players: int = 8,
    default_player_count: int = 5,
    supported_agent_type: str = DEFAULT_AGENT_TYPE,
    default_ruleset_id: str = "default",
    advance_until_input_max_steps: int = 64,
) -> GameUseCaseConfig:
    return GameUseCaseConfig(
        min_players=min_players,
        max_players=max_players,
        default_player_count=default_player_count,
        supported_agent_type=supported_agent_type,
        default_ruleset_id=default_ruleset_id,
        advance_until_input_max_steps=advance_until_input_max_steps,
    )


def local_rules_definition() -> LocalRulesDefinition:
    return LocalRulesDefinition(
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
                        "{{available_actions}} {{observation_json}} {{format_instructions}}"
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


def create_command(**values: object) -> CreateGameCommand:
    values.setdefault("role_counts", DEFAULT_ROLE_COUNTS)
    values.setdefault("rules", local_rules_definition())
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


def test_default_ruleset_returns_business_identifiers_only() -> None:
    deps, _repository = dependencies(
        config=usecase_config(
            min_players=4,
            max_players=10,
            default_player_count=5,
            supported_agent_type=DEFAULT_AGENT_TYPE,
            default_ruleset_id="custom",
        )
    )
    result = GameUseCases.get_default_ruleset(
        deps.config,
        deps.game_definitions,
        deps.llm_definitions,
    )

    assert result.player_count == {"min": 4, "max": 10}
    assert set(result.roles) == {"villager", "werewolf", "seer", "knight"}
    assert result.default_role_counts == DEFAULT_ROLE_COUNTS
    assert result.default_rules == local_rules_definition()


def test_create_game_generates_player_ids_and_sanitizes_public_events() -> None:
    deps, repository = dependencies()

    result = GameUseCases(deps).create_game_run(create_command(seed=42))

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
    use_cases = GameUseCases(deps)

    first = use_cases.create_game_run(create_command(seed=10))
    second = use_cases.create_game_run(create_command(seed=10))
    third = use_cases.create_game_run(create_command(seed=11))

    first_names = [player["name"] for player in first.state["players"]]
    second_names = [player["name"] for player in second.state["players"]]
    third_names = [player["name"] for player in third.state["players"]]

    assert first_names == second_names
    assert first_names != third_names
    assert len(set(first_names)) == 5
    assert not any(str(name).startswith("Player ") for name in first_names)


def test_create_game_returns_control_token_for_requested_human_seat() -> None:
    deps, _repository = dependencies()

    result = GameUseCases(deps).create_game_run(
        create_command(human_player_id="player-1", seed=42),
    )

    assert set(result.control_tokens or {}) == {"player-1"}


def test_reveal_returns_roles_and_private_resolution_without_changing_public_state() -> None:
    deps, _repository = dependencies()
    use_cases = GameUseCases(deps)
    created = use_cases.create_game_run(create_command(seed=1))
    use_cases.advance_game_run(AdvanceGameRunCommand(game_id=created.game_id))

    reveal = use_cases.get_game_reveal(GetGameRevealQuery(game_id=created.game_id))
    public_state = use_cases.get_game_run(GetGameRunQuery(game_id=created.game_id))

    assert reveal.role_counts == DEFAULT_ROLE_COUNTS
    assert {player.role for player in reveal.players} >= {"werewolf", "villager"}
    assert reveal.nights
    assert "role" in json.dumps(reveal.model_dump(mode="json"))
    assert "role" not in json.dumps(public_state.model_dump(mode="json"))


def test_create_game_rejects_out_of_range_role_count_total() -> None:
    deps, _repository = dependencies()

    with pytest.raises(GameError):
        GameUseCases(deps).create_game_run(
            create_command(role_counts={"werewolf": 1, "villager": 3})
        )


def test_game_id_is_parsed_and_validated_inside_usecase() -> None:
    deps, _repository = dependencies()

    with pytest.raises(InvalidGameIdError):
        GameUseCases(deps).get_game_run(GetGameRunQuery(game_id="not-a-uuid"))

    with pytest.raises(GameNotFoundError):
        GameUseCases(deps).get_game_run(GetGameRunQuery(game_id=str(uuid4())))


def test_advance_game_delegates_core_progression_and_returns_public_payloads() -> None:
    telemetry = CollectingTelemetrySink()
    deps, repository = dependencies(telemetry=telemetry)
    use_cases = GameUseCases(deps)
    created = use_cases.create_game_run(create_command(seed=1))

    advanced = use_cases.advance_game_run(AdvanceGameRunCommand(game_id=created.game_id))
    timeline = use_cases.get_game_timeline(GetGameTimelineQuery(game_id=created.game_id, after=0))

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
    assert "game.phase.drive_started" in [event.action for event in telemetry.events]
    assert "game.phase.advance_completed" in [event.action for event in telemetry.events]
    assert all("private_state" not in event.fields for event in telemetry.events)
    agent_events = [
        event for event in telemetry.events if event.action == "game.agent_action.generated"
    ]
    assert agent_events
    assert all("player_id" not in event.fields for event in agent_events)
    assert all("game_action_type" not in event.fields for event in agent_events)
    assert all("agent_type" in event.fields for event in agent_events)


def test_discussion_timeline_contains_fake_speeches_without_private_fields() -> None:
    deps, _repository = dependencies()
    use_cases = GameUseCases(deps)
    created = use_cases.create_game_run(create_command(seed=1))

    use_cases.advance_game_run(AdvanceGameRunCommand(game_id=created.game_id))
    advanced = use_cases.advance_game_run(AdvanceGameRunCommand(game_id=created.game_id))
    serialized = json.dumps(advanced.timeline)
    speech_events = [item for item in advanced.timeline if item["event_type"] == "speech_recorded"]

    assert speech_events
    assert all("hello from" in item["payload"]["message"] for item in speech_events)
    assert "role_counts" not in serialized
    assert "target_role" not in serialized
    assert "target_faction" not in serialized


def test_submit_manual_action_emits_sanitized_telemetry() -> None:
    telemetry = CollectingTelemetrySink()
    deps, _repository = dependencies(telemetry=telemetry)
    use_cases = GameUseCases(deps)
    created = use_cases.create_game_run(
        create_command(human_player_id="player-1", seed=2),
    )
    control_token = created.control_tokens["player-1"] if created.control_tokens else ""
    use_cases.advance_until_input(AdvanceUntilInputCommand(game_id=created.game_id, max_steps=8))
    observation = use_cases.get_player_observation(
        GetPlayerObservationQuery(
            game_id=created.game_id,
            player_id="player-1",
            control_token=control_token,
        )
    )
    action_type = str(observation.observation["available_actions"][0])
    target_id = None
    message = None
    if action_type == "speech":
        message = "hello"
    else:
        target_id = _first_target(observation.observation, player_id="player-1")

    use_cases.submit_player_action(
        PlayerActionCommand(
            game_id=created.game_id,
            player_id="player-1",
            control_token=control_token,
            type=action_type,
            target_id=target_id,
            message=message,
        )
    )

    event = next(
        event for event in telemetry.events if event.action == "game.manual_action.accepted"
    )
    assert event.fields["has_message"] is bool(message)
    assert "player_id" not in event.fields
    assert "game_action_type" not in event.fields
    assert "control_token" not in event.fields
    assert "message" not in event.fields


def test_manual_input_blocks_advance_and_duplicate_actions() -> None:
    deps, _repository = dependencies()
    use_cases = GameUseCases(deps)
    created = use_cases.create_game_run(
        create_command(human_player_id="player-1", seed=2),
    )
    control_token = created.control_tokens["player-1"] if created.control_tokens else ""

    stopped = use_cases.advance_until_input(
        AdvanceUntilInputCommand(game_id=created.game_id, max_steps=8)
    )
    assert stopped.stop_reason == "manual_input_required"
    with pytest.raises(GameError):
        use_cases.advance_game_run(AdvanceGameRunCommand(game_id=created.game_id))

    observation = use_cases.get_player_observation(
        GetPlayerObservationQuery(
            game_id=created.game_id,
            player_id="player-1",
            control_token=control_token,
        )
    )
    action_type = str(observation.observation["available_actions"][0])
    target_id = None
    if action_type != "speech":
        target_id = _first_target(observation.observation, player_id="player-1")
    command = PlayerActionCommand(
        game_id=created.game_id,
        player_id="player-1",
        control_token=control_token,
        type=action_type,
        target_id=target_id,
        message="hello" if action_type == "speech" else None,
    )

    use_cases.submit_player_action(command)
    with pytest.raises(GameError):
        use_cases.submit_player_action(command)


def test_list_games_and_turns_return_public_read_models() -> None:
    deps, _repository = dependencies()
    use_cases = GameUseCases(deps)
    created = use_cases.create_game_run(create_command(seed=1))
    use_cases.advance_game_run(AdvanceGameRunCommand(game_id=created.game_id))

    runs = use_cases.list_game_runs(ListGameRunsQuery(limit=10))
    timeline = use_cases.get_game_timeline(GetGameTimelineQuery(game_id=created.game_id))

    assert runs.runs[0]["game_id"] == created.game_id
    assert runs.runs[0]["turn_count"] == len(timeline.items)
    assert timeline.items
    assert "role_counts" not in json.dumps(timeline.model_dump(mode="json"))
