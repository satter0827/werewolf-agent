import random
from dataclasses import FrozenInstanceError, dataclass, field, replace

import pytest

import werewolf_agent.domain as domain_api
from werewolf_agent.domain import (
    Game,
    GameSetup,
    RuleRegistry,
    RuleSetDefinition,
    RuleViolation,
)
from werewolf_agent.domain.rules.base import RuleContext, VictoryPolicy
from werewolf_agent.domain.state import (
    ABILITY_GUARD,
    ABILITY_INSPECT,
    ABILITY_NIGHT_ATTACK,
    ABILITY_PACK_KNOWLEDGE,
    FACTION_VILLAGE,
    FACTION_WEREWOLF,
    AbilityDefinition,
    Action,
    ActionType,
    GameConfig,
    GameEvent,
    GameState,
    LocalRules,
    PendingActions,
    Phase,
    Player,
    PlayerStatus,
    RoleCatalog,
    RoleDefinition,
    WinResult,
)

ROLE_PLAIN = "plain"
ROLE_SHADOW = "shadow"
ROLE_READER = "reader"
ROLE_SHIELD = "shield"


def test_public_domain_api_can_create_restore_and_progress_a_game() -> None:
    """公開moduleだけでheadless engineの基本lifecycleを実行できる。"""
    local = domain_api.LocalRules(
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
    roles = domain_api.RoleCatalog(
        roles={
            "villager": domain_api.RoleDefinition(faction="village"),
            "werewolf": domain_api.RoleDefinition(
                faction="werewolf",
                abilities=("night_attack",),
            ),
        }
    )
    definition = domain_api.RuleSetDefinition(
        player_count=3,
        role_counts={"villager": 2, "werewolf": 1},
        rules=local,
        roles=roles,
        abilities={
            "night_attack": domain_api.AbilityDefinition(
                phase=domain_api.Phase.NIGHT,
                action=domain_api.ActionType.WEREWOLF_ATTACK,
                validation_policy="standard",
                resolution_policy="standard",
                target_policy="other_alive_non_pack",
                start_day=1,
            )
        },
    )
    rules = domain_api.RuleRegistry.standard().build(definition)
    game = domain_api.Game.create(
        domain_api.GameSetup(
            players=tuple(
                domain_api.Player(id=f"p{index}", name=f"Player {index}") for index in range(1, 4)
            )
        ),
        rules=rules,
        random=random.Random(1),
    )

    restored = domain_api.Game.restore(game.snapshot(), rules=rules)
    actor = next(
        player.id
        for player in restored.snapshot().players.values()
        if restored.view_for(player.id).available_actions
    )
    target = restored.view_for(actor).legal_targets[domain_api.ActionType.WEREWOLF_ATTACK][0]
    events = restored.submit(domain_api.Action.attack(actor, target))

    assert events
    assert restored.snapshot().pending_actions.night_actions[actor].target_id == target


@dataclass
class HeadlessRun:
    game: Game
    rng: random.Random
    events: list[GameEvent] = field(default_factory=list)

    @property
    def snapshot(self) -> GameState:
        return self.game.snapshot()

    def observe(self, player_id: str):
        return self.game.view_for(player_id)

    def submit(self, action: Action) -> None:
        self.events.extend(self.game.submit(action))

    def advance(self) -> GameState:
        self.events.extend(self.game.advance(self.rng))
        return self.game.snapshot()


def role_catalog() -> RoleCatalog:
    return RoleCatalog(
        roles={
            ROLE_PLAIN: RoleDefinition(faction=FACTION_VILLAGE, abilities=()),
            ROLE_SHADOW: RoleDefinition(
                faction=FACTION_WEREWOLF,
                abilities=(ABILITY_NIGHT_ATTACK, ABILITY_PACK_KNOWLEDGE),
            ),
            ROLE_READER: RoleDefinition(faction=FACTION_VILLAGE, abilities=(ABILITY_INSPECT,)),
            ROLE_SHIELD: RoleDefinition(faction=FACTION_VILLAGE, abilities=(ABILITY_GUARD,)),
        }
    )


def local_rules(*, random_tie: bool = False) -> LocalRules:
    return LocalRules(
        day_speech_limit_per_player=1,
        allow_self_vote=False,
        allow_vote_revision=False,
        allow_night_action_revision=False,
        enable_first_night_attack=True,
        enable_no_elimination_on_tie=not random_tie,
        enable_random_elimination_on_tie=random_tie,
        allow_knight_self_guard=True,
        allow_knight_repeat_guard=True,
        allow_seer_self_inspect=False,
        allow_werewolf_friendly_fire=False,
        reveal_role_on_death=False,
    )


def mvp_config(*, random_tie: bool = False) -> GameConfig:
    return GameConfig(
        player_count=5,
        role_counts={
            ROLE_SHADOW: 1,
            ROLE_READER: 1,
            ROLE_SHIELD: 1,
            ROLE_PLAIN: 2,
        },
        rules=local_rules(random_tie=random_tie),
        roles=role_catalog(),
        abilities=ability_definitions(),
    )


def ability_definitions() -> dict[str, AbilityDefinition]:
    return {
        ABILITY_NIGHT_ATTACK: AbilityDefinition(
            phase=Phase.NIGHT,
            action=ActionType.WEREWOLF_ATTACK,
            validation_policy="standard",
            resolution_policy="standard",
            target_policy="other_alive_non_pack",
            start_day=1,
        ),
        ABILITY_PACK_KNOWLEDGE: AbilityDefinition(
            phase=Phase.NIGHT,
            action=ActionType.PASS,
            validation_policy="standard",
            resolution_policy="standard",
            target_policy="none",
            start_day=1,
        ),
        ABILITY_INSPECT: AbilityDefinition(
            phase=Phase.NIGHT,
            action=ActionType.SEER_INSPECT,
            validation_policy="standard",
            resolution_policy="standard",
            target_policy="other_alive",
            start_day=1,
        ),
        ABILITY_GUARD: AbilityDefinition(
            phase=Phase.NIGHT,
            action=ActionType.KNIGHT_GUARD,
            validation_policy="standard",
            resolution_policy="standard",
            target_policy="alive",
            start_day=1,
        ),
    }


def fixed_players() -> list[Player]:
    return [
        Player(id="p1", name="Alice", role=ROLE_SHADOW),
        Player(id="p2", name="Bob", role=ROLE_READER),
        Player(id="p3", name="Chika", role=ROLE_SHIELD),
        Player(id="p4", name="Dan", role=ROLE_PLAIN),
        Player(id="p5", name="Eve", role=ROLE_PLAIN),
    ]


def rule_set_for(config: GameConfig):
    return RuleRegistry.standard().build(
        RuleSetDefinition(
            player_count=config.player_count,
            role_counts=dict(config.role_counts),
            rules=config.rules,
            roles=config.roles,
            abilities=dict(config.abilities),
            phases=tuple(phase.value for phase in config.phase_order),
        )
    )


def start_fixed_run(
    *,
    random_tie: bool = False,
    seed: int = 7,
) -> HeadlessRun:
    rng = random.Random(seed)
    game = Game.create(
        GameSetup(players=tuple(fixed_players())),
        rules=rule_set_for(mvp_config(random_tie=random_tie)),
        random=rng,
    )
    return HeadlessRun(
        game=game,
        rng=rng,
        events=list(game.creation_events),
    )


def play_random_legal_game(seed: int) -> HeadlessRun:
    """公開された合法手だけをseed固定で選び、ゲームを終了まで進める。"""
    run = start_fixed_run(random_tie=bool(seed % 2), seed=seed)
    for _step in range(64):
        if run.snapshot.is_finished:
            return run
        player_ids = list(run.snapshot.players)
        run.rng.shuffle(player_ids)
        for player_id in player_ids:
            observation = run.observe(player_id)
            if not observation.available_actions:
                continue
            action_type = run.rng.choice(observation.available_actions)
            if action_type is ActionType.SPEECH:
                action = Action.speech(player_id, f"seed-{seed}")
            else:
                targets = observation.legal_targets[action_type]
                target_id = run.rng.choice(targets)
                action = {
                    ActionType.VOTE: Action.vote,
                    ActionType.WEREWOLF_ATTACK: Action.attack,
                    ActionType.SEER_INSPECT: Action.inspect,
                    ActionType.KNIGHT_GUARD: Action.guard,
                }[action_type](player_id, target_id)
            run.submit(action)
        run.advance()
        assert set(run.snapshot.players) == set(player_ids)
        assert run.snapshot.day >= 1
    pytest.fail(f"seed={seed}のゲームが64 phase以内に終了しませんでした。")


@pytest.mark.monkey
def test_domain_state_transitions_are_stable_for_64_seeded_runs() -> None:
    """合法手をランダム選択する64ゲームを再現可能に完走する。"""
    for seed in range(64):
        run = play_random_legal_game(seed)
        assert run.snapshot.phase is Phase.FINISHED
        assert run.snapshot.win_result is not None
        assert run.events


@pytest.mark.benchmark
def test_core_game_creation_benchmark(benchmark) -> None:
    """domain coreの生成性能を継続観測する。"""
    result = benchmark(start_fixed_run)

    assert result.snapshot.phase is Phase.NIGHT


def test_public_state_and_nested_collections_are_immutable() -> None:
    snapshot = start_fixed_run().snapshot

    with pytest.raises(FrozenInstanceError):
        snapshot.day = 99  # type: ignore[misc]
    with pytest.raises(TypeError):
        snapshot.players["p1"] = snapshot.players["p2"]  # type: ignore[index]
    with pytest.raises(TypeError):
        snapshot.pending_actions.votes["p1"] = Action.vote("p1", "p2")  # type: ignore[index]
    internal_players = snapshot.players._values
    with pytest.raises(TypeError):
        internal_players["p1"] = snapshot.players["p2"]


def test_restored_state_rejects_aggregate_invariant_violations() -> None:
    snapshot = start_fixed_run().snapshot
    first = snapshot.players["p1"]
    replacement_role = next(
        player.role for player in snapshot.players.values() if player.role != first.role
    )

    with pytest.raises(ValueError, match="assigned roles"):
        replace(
            snapshot,
            players={**snapshot.players, first.id: replace(first, role=replacement_role)},
        )
    with pytest.raises(ValueError, match="player count"):
        replace(snapshot, players=dict(tuple(snapshot.players.items())[1:]))
    with pytest.raises(ValueError, match="pending action"):
        replace(
            snapshot,
            pending_actions=PendingActions(night_actions={"ghost": Action.pass_("ghost")}),
        )
    with pytest.raises(ValueError, match="finished phase"):
        replace(snapshot, phase=Phase.FINISHED)
    with pytest.raises(ValueError, match="winning faction"):
        replace(
            snapshot,
            phase=Phase.FINISHED,
            win_result=WinResult(
                winner=FACTION_VILLAGE,
                reason="invalid winners",
                day=snapshot.day,
                winning_player_ids=(),
            ),
        )
    with pytest.raises(ValueError, match="death marker"):
        replace(first, status=PlayerStatus.DEAD)
    with pytest.raises(ValueError, match="Unsupported faction"):
        WinResult(winner="other", reason="invalid", day=1, winning_player_ids=())


@pytest.mark.monkey
@pytest.mark.deep
def test_domain_state_transitions_are_stable_for_256_seeded_runs() -> None:
    """deepでは256ゲームを完走し、異なる終局へ到達する。"""
    outcomes: set[tuple[str | None, tuple[str, ...]]] = set()
    for seed in range(256):
        run = play_random_legal_game(seed)
        outcomes.add(
            (
                run.snapshot.winner_id,
                tuple(
                    player.id
                    for player in run.snapshot.players.values()
                    if player.status is PlayerStatus.DEAD
                ),
            )
        )
    assert len(outcomes) >= 2


def advance_to_voting(run: HeadlessRun) -> None:
    complete_night(run)
    run.advance()
    run.advance()
    assert run.snapshot.phase is Phase.VOTING


def complete_night(run: HeadlessRun) -> None:
    run.submit(Action.attack("p1", "p4"))
    run.submit(Action.inspect("p2", "p1"))
    run.submit(Action.guard("p3", "p4"))


def test_game_config_validates_role_counts() -> None:
    with pytest.raises(ValueError):
        GameConfig(
            player_count=5,
            role_counts={ROLE_SHADOW: 1, ROLE_PLAIN: 3},
            rules=local_rules(),
            roles=role_catalog(),
            abilities=ability_definitions(),
        )


def test_start_game_is_headless_and_returns_events() -> None:
    run = start_fixed_run()

    snapshot = run.snapshot

    assert snapshot.phase is Phase.NIGHT
    assert snapshot.day == 1
    assert snapshot.players["p1"].role == ROLE_SHADOW
    assert run.events[0].event_type == "game_started"
    assert run.events[0].payload["role_counts"] == {
        ROLE_SHADOW: 1,
        ROLE_READER: 1,
        ROLE_SHIELD: 1,
        ROLE_PLAIN: 2,
    }


def test_observation_hides_secret_roles_but_shows_allowed_knowledge() -> None:
    run = start_fixed_run()

    seer_observation = run.observe("p2")
    wolf_observation = run.observe("p1")

    assert seer_observation.known_roles == {"p2": ROLE_READER}
    assert {player.id: player.role for player in seer_observation.players} == {
        "p1": None,
        "p2": ROLE_READER,
        "p3": None,
        "p4": None,
        "p5": None,
    }
    assert wolf_observation.known_roles == {"p1": ROLE_SHADOW}


def test_night_actions_resolve_guard_and_private_seer_knowledge() -> None:
    run = start_fixed_run()

    run.submit(Action.attack("p1", "p4"))
    run.submit(Action.inspect("p2", "p1"))
    run.submit(Action.guard("p3", "p4"))
    snapshot = run.advance()

    assert snapshot.phase is Phase.DAY_DISCUSSION
    assert snapshot.players["p4"].status is PlayerStatus.ALIVE
    assert snapshot.history.nights[-1].protected_player_id == "p4"
    assert snapshot.history.nights[-1].killed_player_id is None
    assert run.events[-2].event_type == "night_resolved"
    assert run.events[-2].payload == {"killed_player_id": None}
    assert run.observe("p2").known_roles["p1"] == ROLE_SHADOW
    assert "p1" not in run.observe("p4").known_roles


def test_vote_resolution_eliminates_player_and_finishes_game() -> None:
    run = start_fixed_run()
    advance_to_voting(run)

    for voter_id in ["p2", "p3", "p4", "p5"]:
        run.submit(Action.vote(voter_id, "p1"))
    run.submit(Action.vote("p1", "p5"))
    snapshot = run.advance()

    assert snapshot.phase is Phase.FINISHED
    assert snapshot.players["p1"].status is PlayerStatus.DEAD
    assert snapshot.history.votes[-1].eliminated_player_id == "p1"
    assert snapshot.win_result is not None
    assert snapshot.win_result.winner == FACTION_VILLAGE


def test_vote_submission_is_private_until_votes_are_resolved() -> None:
    run = start_fixed_run()
    advance_to_voting(run)

    events = run.game.submit(Action.vote("p1", "p5"))

    assert [event.event_type for event in events] == ["vote_submitted"]
    assert events[0].visibility.value == "player_private"
    assert events[0].payload == {"target_id": "p5"}


def test_vote_tie_policy_can_leave_everyone_alive() -> None:
    run = start_fixed_run()
    advance_to_voting(run)

    run.submit(Action.vote("p1", "p4"))
    run.submit(Action.vote("p2", "p4"))
    run.submit(Action.vote("p3", "p5"))
    run.submit(Action.vote("p4", "p5"))
    run.submit(Action.vote("p5", "p1"))
    snapshot = run.advance()

    assert snapshot.phase is Phase.NIGHT
    assert snapshot.day == 2
    assert snapshot.history.votes[-1].eliminated_player_id is None
    assert snapshot.history.votes[-1].tied_player_ids == ("p4", "p5")
    assert snapshot.history.votes[-1].missing_voter_ids == ()


def test_invalid_actions_raise_safe_game_errors() -> None:
    run = start_fixed_run()

    with pytest.raises(RuleViolation):
        run.submit(Action.vote("p1", "p2"))

    with pytest.raises(RuleViolation):
        run.submit(Action.inspect("p4", "p1"))


def test_day_speech_is_only_recorded_during_discussion() -> None:
    run = start_fixed_run()

    with pytest.raises(RuleViolation):
        run.submit(Action.speech("p2", "too early"))

    complete_night(run)
    run.advance()
    run.submit(Action.speech("p2", "I have a read."))

    assert run.snapshot.history.speeches[-1].message == "I have a read."
    assert run.snapshot.history.speeches[-1].day == 1
    assert run.observe("p2").available_actions == ()
    with pytest.raises(RuleViolation):
        run.submit(Action.speech("p2", "same day duplicate"))


def test_day_speech_limit_resets_on_next_day() -> None:
    run = start_fixed_run()
    complete_night(run)
    run.advance()
    run.submit(Action.speech("p2", "day one"))
    run.advance()
    run.submit(Action.vote("p1", "p4"))
    run.submit(Action.vote("p2", "p4"))
    run.submit(Action.vote("p3", "p5"))
    run.submit(Action.vote("p4", "p5"))
    run.submit(Action.vote("p5", "p1"))
    run.advance()
    complete_night(run)
    run.advance()

    assert run.snapshot.phase is Phase.DAY_DISCUSSION
    assert run.snapshot.day == 2
    assert run.observe("p2").available_actions == (ActionType.SPEECH,)


def test_day_speech_limit_is_rule_driven() -> None:
    config = replace(
        mvp_config(),
        rules=replace(local_rules(), day_speech_limit_per_player=2),
    )
    game = Game.create(
        GameSetup(players=tuple(fixed_players())),
        rules=rule_set_for(config),
        random=random.Random(7),
    )
    run = HeadlessRun(
        game=game,
        rng=random.Random(7),
        events=list(game.creation_events),
    )

    complete_night(run)
    run.advance()
    run.submit(Action.speech("p2", "first"))
    assert run.observe("p2").available_actions == (ActionType.SPEECH,)
    run.submit(Action.speech("p2", "second"))

    assert run.observe("p2").available_actions == ()
    with pytest.raises(RuleViolation):
        run.submit(Action.speech("p2", "third"))


def test_vote_and_night_actions_are_single_submission_by_default() -> None:
    run = start_fixed_run()

    run.submit(Action.attack("p1", "p4"))
    with pytest.raises(RuleViolation):
        run.submit(Action.attack("p1", "p5"))

    run.submit(Action.inspect("p2", "p1"))
    run.submit(Action.guard("p3", "p4"))
    run.advance()
    run.advance()
    run.submit(Action.vote("p2", "p1"))
    assert run.observe("p2").available_actions == ()
    with pytest.raises(RuleViolation):
        run.submit(Action.vote("p2", "p4"))


def test_game_aggregate_rejects_advance_until_required_actions_exist() -> None:
    definition = RuleSetDefinition(
        player_count=5,
        role_counts=mvp_config().role_counts,
        rules=local_rules(),
        roles=role_catalog(),
        abilities=ability_definitions(),
    )
    game = Game.create(
        GameSetup(players=tuple(fixed_players())),
        rules=RuleRegistry.standard().build(definition),
        random=random.Random(7),
    )

    with pytest.raises(RuleViolation, match="Required actions are missing"):
        game.advance(random.Random(7))

    game.submit(Action.attack("p1", "p4"))
    game.submit(Action.inspect("p2", "p1"))
    game.submit(Action.guard("p3", "p4"))
    events = game.advance(random.Random(7))

    assert game.snapshot().phase is Phase.DAY_DISCUSSION
    assert any(event.event_type == "night_resolved" for event in events)


def test_game_aggregate_failed_submission_does_not_change_state() -> None:
    definition = RuleSetDefinition(
        player_count=5,
        role_counts=mvp_config().role_counts,
        rules=local_rules(),
        roles=role_catalog(),
        abilities=ability_definitions(),
    )
    game = Game.create(
        GameSetup(players=tuple(fixed_players())),
        rules=RuleRegistry.standard().build(definition),
        random=random.Random(7),
    )
    before = game.snapshot()

    with pytest.raises(RuleViolation):
        game.submit(Action.vote("p1", "p2"))

    assert game.snapshot() == before


def test_same_seed_and_actions_produce_the_same_events_and_state() -> None:
    rules = rule_set_for(mvp_config())
    setup = GameSetup(
        players=tuple(Player(id=f"p{index}", name=f"Player {index}") for index in range(1, 6))
    )
    first = Game.create(setup, rules=rules, random=random.Random(17))
    second = Game.create(setup, rules=rules, random=random.Random(17))

    assert first.creation_events == second.creation_events
    assert first.snapshot() == second.snapshot()

    for game in (first, second):
        views = {player_id: game.view_for(player_id) for player_id in game.snapshot().players}
        for player_id, view in views.items():
            for action_type in view.available_actions:
                targets = view.legal_targets.get(action_type, [])
                if targets:
                    game.submit(
                        Action(
                            type=action_type,
                            player_id=player_id,
                            target_id=targets[0],
                        )
                    )

    assert first.advance(random.Random(29)) == second.advance(random.Random(29))
    assert first.snapshot() == second.snapshot()


def test_observation_contains_only_domain_validated_targets() -> None:
    run = start_fixed_run()

    wolf = run.observe("p1")
    seer = run.observe("p2")
    knight = run.observe("p3")

    assert wolf.legal_targets[ActionType.WEREWOLF_ATTACK] == ("p2", "p3", "p4", "p5")
    assert seer.legal_targets[ActionType.SEER_INSPECT] == ("p1", "p3", "p4", "p5")
    assert knight.legal_targets[ActionType.KNIGHT_GUARD] == ("p1", "p2", "p3", "p4", "p5")


def test_game_aggregate_uses_registered_victory_policy() -> None:
    class NeverVictoryPolicy(VictoryPolicy):
        def evaluate(self, context: RuleContext) -> WinResult | None:
            _ = context
            return None

    registry = RuleRegistry.standard()
    registry.register_victory("never", NeverVictoryPolicy)
    definition = RuleSetDefinition(
        player_count=5,
        role_counts=mvp_config().role_counts,
        rules=local_rules(),
        roles=role_catalog(),
        abilities=ability_definitions(),
        victory_policy="never",
    )
    game = Game.create(
        GameSetup(players=tuple(fixed_players())),
        rules=registry.build(definition),
        random=random.Random(7),
    )
    game.submit(Action.attack("p1", "p4"))
    game.submit(Action.inspect("p2", "p1"))
    game.submit(Action.guard("p3", "p4"))
    game.advance(random.Random(7))
    game.advance(random.Random(7))
    for voter_id in ["p2", "p3", "p4", "p5"]:
        game.submit(Action.vote(voter_id, "p1"))
    game.submit(Action.vote("p1", "p5"))

    events = game.advance(random.Random(7))

    assert game.snapshot().phase is Phase.NIGHT
    assert game.snapshot().win_result is None
    assert not any(event.event_type == "game_finished" for event in events)


def test_rule_set_uses_configured_phase_order() -> None:
    definition = RuleSetDefinition(
        player_count=5,
        role_counts=mvp_config().role_counts,
        rules=local_rules(),
        roles=role_catalog(),
        abilities=ability_definitions(),
        phases=("day_discussion", "voting", "night"),
    )
    game = Game.create(
        GameSetup(players=tuple(fixed_players())),
        rules=RuleRegistry.standard().build(definition),
        random=random.Random(7),
    )

    assert game.snapshot().phase is Phase.DAY_DISCUSSION
    game.advance(random.Random(7))
    assert game.snapshot().phase is Phase.VOTING


def test_ability_start_day_controls_available_actions() -> None:
    config = mvp_config()
    delayed_inspection = replace(config.abilities[ABILITY_INSPECT], start_day=2)
    abilities = {**config.abilities, ABILITY_INSPECT: delayed_inspection}
    definition = RuleSetDefinition(
        player_count=5,
        role_counts=config.role_counts,
        rules=local_rules(),
        roles=role_catalog(),
        abilities=abilities,
    )
    game = Game.create(
        GameSetup(players=tuple(fixed_players())),
        rules=RuleRegistry.standard().build(definition),
        random=random.Random(7),
    )

    assert ActionType.SEER_INSPECT not in game.view_for("p2").available_actions
    assert delayed_inspection.start_day == 2
