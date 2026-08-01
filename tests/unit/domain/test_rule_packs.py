"""外部Rule Packの明示注入と勝敗policy契約を検証する."""

from __future__ import annotations

import random
from collections.abc import Mapping

import pytest

from werewolf_agent.domain import (
    AbilityDefinition,
    AbilityPolicy,
    Action,
    CompiledRuleSet,
    CoreRulePack,
    DeathReaction,
    DeathReactionResolution,
    DiscussionConfig,
    DiscussionResolution,
    DiscussionRound,
    DiscussionRoundKind,
    Game,
    GameError,
    GameSetup,
    GameState,
    KnowledgeClaim,
    KnowledgeResolution,
    LifecycleConfig,
    NightConfig,
    NightResolution,
    Phase,
    Player,
    RoleCatalog,
    RoleDefinition,
    RulePackManifest,
    RulePolicyRegistry,
    RuleSetDefinition,
    VoteResult,
    VotingConfig,
    VotingPolicy,
    WinResult,
)
from werewolf_agent.domain.rule_packs import RULE_PACK_CONTRACT_VERSION
from werewolf_agent.domain.rules.discussion import CoreDiscussionPolicy


def _definition() -> RuleSetDefinition:
    return RuleSetDefinition(
        player_count=3,
        role_counts={"villager": 2, "werewolf": 1},
        discussion=DiscussionConfig(),
        voting=VotingConfig(),
        night=NightConfig(),
        lifecycle=LifecycleConfig(
            starting_phase="day_discussion",
            require_all_actions_before_advance=False,
        ),
        roles=RoleCatalog(
            {
                "villager": RoleDefinition("village", "village"),
                "werewolf": RoleDefinition("werewolf", "werewolf"),
            }
        ),
        abilities={},
    )


class ImmediateVillageVictory:
    """最初の進行で村人勝利を返す外部test policy."""

    def evaluate(self, state: GameState) -> WinResult:
        """現在の村人陣営playerを勝者として返す."""
        winners = tuple(
            player.id
            for player in state.players.values()
            if player.role is not None
            and state.config.roles.victory_team_for_role(player.role) == "village"
        )
        return WinResult(
            winner="village",
            reason="external_test_condition",
            day=state.day,
            winning_player_ids=winners,
        )


class ExternalVictoryPack:
    """Coreのconfig構築と外部勝敗policyを組み合わせるtest provider."""

    @property
    def manifest(self) -> RulePackManifest:
        """外部実装を識別するmanifestを返す."""
        return RulePackManifest(
            provider_id="external-victory",
            contract_version=RULE_PACK_CONTRACT_VERSION,
            implementation_version="1.0.0",
            fingerprint="1" * 64,
        )

    def compile(self, definition: RuleSetDefinition) -> CompiledRuleSet:
        """Core configへ外部勝敗policyを明示注入する."""
        core = CoreRulePack().compile(definition)
        return CompiledRuleSet(
            config=core.config,
            manifest=self.manifest,
            ability_policy=core.ability_policy,
            voting_policy=core.voting_policy,
            discussion_policy=core.discussion_policy,
            victory_policy=ImmediateVillageVictory(),
        )


class InvalidVictoryPolicy:
    """Stateと矛盾する勝者一覧を返すfault policy."""

    def evaluate(self, state: GameState) -> WinResult:
        """村人勝利へ人狼playerだけを含めた不正Outcomeを返す."""
        wolf_id = next(
            player.id
            for player in state.players.values()
            if player.role is not None
            and state.config.roles.victory_team_for_role(player.role) == "werewolf"
        )
        return WinResult(
            winner="village",
            reason="invalid_external_outcome",
            day=state.day,
            winning_player_ids=(wolf_id,),
        )


class RedirectVotingPolicy:
    """得票数にかかわらずp2を排除する外部test policy."""

    def resolve(
        self,
        state: GameState,
        pending_votes: Mapping[str, Action],
        random: random.Random,
        *,
        vote_round: int,
    ) -> VoteResult:
        """入力票を保持しつつ外部意味論の排除Outcomeを返す."""
        del random
        votes = {player_id: str(action.target_id) for player_id, action in pending_votes.items()}
        return VoteResult(
            day=state.day,
            votes=votes,
            reasons={player_id: action.reason or "" for player_id, action in pending_votes.items()},
            counts={"p1": 2, "p2": 1},
            tied_player_ids=("p1",),
            missing_voter_ids=(),
            eliminated_player_id="p2",
            tie_break_policy="external_redirect",
            round=vote_round,
        )


class InvalidVotingPolicy:
    """存在しないplayerを排除するfault policy."""

    def resolve(
        self,
        state: GameState,
        pending_votes: Mapping[str, Action],
        random: random.Random,
        *,
        vote_round: int,
    ) -> VoteResult:
        """Domain invariantに反する排除Outcomeを返す."""
        del random
        return VoteResult(
            day=state.day,
            votes={player_id: str(action.target_id) for player_id, action in pending_votes.items()},
            reasons={player_id: action.reason or "" for player_id, action in pending_votes.items()},
            counts={"p1": 2, "p2": 1},
            tied_player_ids=("p1",),
            missing_voter_ids=(),
            eliminated_player_id="unknown",
            tie_break_policy="invalid",
            round=vote_round,
        )


class SkipResponseDiscussionPolicy:
    """openingの公開後に必要なresponseを省略するfault policy."""

    def __init__(self) -> None:
        self._core = CoreDiscussionPolicy()

    def start(self, state: GameState) -> DiscussionRound:
        """組み込みと同じopeningから開始する."""
        return self._core.start(state)

    def resolve(
        self,
        state: GameState,
        round_: DiscussionRound,
        submissions: Mapping[str, Action],
    ) -> DiscussionResolution:
        """opening発言を保持したままresponseを不正に省略する."""
        resolution = self._core.resolve(state, round_, submissions)
        if round_.kind is DiscussionRoundKind.OPENING and resolution.speeches:
            return DiscussionResolution(resolution.speeches, None, True)
        return resolution


class InvalidStartDiscussionPolicy(SkipResponseDiscussionPolicy):
    """初日をresponseから始めるfault policy."""

    def start(self, state: GameState) -> DiscussionRound:
        """構造化議論の開始条件に反するroundを返す."""
        opening = self._core.start(state)
        return DiscussionRound(
            "invalid-response",
            1,
            DiscussionRoundKind.RESPONSE,
            "ordered",
            opening.actor_order,
            reference_ids=("not-published",),
        )


class RedirectAbilityPolicy:
    """提出された攻撃先ではなくp3を死亡させる外部test policy."""

    def resolve_night(
        self,
        state: GameState,
        pending_actions: Mapping[str, Action],
        random: random.Random,
    ) -> NightResolution:
        """入力や乱数を変更せず外部意味論のOutcomeを返す."""
        del state, pending_actions, random
        return NightResolution(attacked_player_ids=("p2",), killed_player_ids=("p3",))

    def resolve_death_reactions(
        self,
        state: GameState,
        newly_dead_player_ids: tuple[str, ...],
        random: random.Random,
    ) -> DeathReactionResolution:
        """死亡反応を発生させない."""
        del state, newly_dead_player_ids, random
        return DeathReactionResolution()

    def resolve_knowledge(self, state: GameState) -> KnowledgeResolution:
        """知識候補を発生させない."""
        del state
        return KnowledgeResolution()


class InvalidAbilityPolicy:
    """存在しないplayerを死亡させるfault policy."""

    def resolve_night(
        self,
        state: GameState,
        pending_actions: Mapping[str, Action],
        random: random.Random,
    ) -> NightResolution:
        """Domain invariantに反するOutcomeを返す."""
        del state, pending_actions
        random.choice(("consumed",))
        return NightResolution(killed_player_ids=("unknown",))

    def resolve_death_reactions(
        self,
        state: GameState,
        newly_dead_player_ids: tuple[str, ...],
        random: random.Random,
    ) -> DeathReactionResolution:
        """死亡反応を発生させない."""
        del state, newly_dead_player_ids, random
        return DeathReactionResolution()

    def resolve_knowledge(self, state: GameState) -> KnowledgeResolution:
        """知識候補を発生させない."""
        del state
        return KnowledgeResolution()


class ExcessPassiveUsePolicy:
    """設定済み上限を超える受動能力使用を返すfault policy."""

    def resolve_night(
        self,
        state: GameState,
        pending_actions: Mapping[str, Action],
        random: random.Random,
    ) -> NightResolution:
        """同じ一回制限能力を二回使用したOutcomeを返す."""
        del state, pending_actions, random
        return NightResolution(passive_uses=(("p2", "immunity"), ("p2", "immunity")))

    def resolve_death_reactions(
        self,
        state: GameState,
        newly_dead_player_ids: tuple[str, ...],
        random: random.Random,
    ) -> DeathReactionResolution:
        """死亡反応を発生させない."""
        del state, newly_dead_player_ids, random
        return DeathReactionResolution()

    def resolve_knowledge(self, state: GameState) -> KnowledgeResolution:
        """知識候補を発生させない."""
        del state
        return KnowledgeResolution()


class SuppressDeathReactionPolicy:
    """Coreの夜解決を保ち、死亡反応だけを抑止する外部test policy."""

    def __init__(self, core: AbilityPolicy) -> None:
        self._core = core

    def resolve_night(
        self,
        state: GameState,
        pending_actions: Mapping[str, Action],
        random: random.Random,
    ) -> NightResolution:
        """夜解決はCoreへ委譲する."""
        return self._core.resolve_night(state, pending_actions, random)

    def resolve_death_reactions(
        self,
        state: GameState,
        newly_dead_player_ids: tuple[str, ...],
        random: random.Random,
    ) -> DeathReactionResolution:
        """死亡反応を明示的に発生させない."""
        del state, newly_dead_player_ids, random
        return DeathReactionResolution()

    def resolve_knowledge(self, state: GameState) -> KnowledgeResolution:
        """知識解決はCoreへ委譲する."""
        return self._core.resolve_knowledge(state)


class InvalidDeathReactionPolicy(SuppressDeathReactionPolicy):
    """生存者を反応所有者として返すfault policy."""

    def resolve_death_reactions(
        self,
        state: GameState,
        newly_dead_player_ids: tuple[str, ...],
        random: random.Random,
    ) -> DeathReactionResolution:
        """Domain invariantに反する反応Outcomeを返す."""
        del state, newly_dead_player_ids
        random.choice(("consumed",))
        return DeathReactionResolution((DeathReaction("p1", "reaction", "p3"),))


class RedirectKnowledgePolicy(SuppressDeathReactionPolicy):
    """Private knowledgeの意味論を外部から変更するtest policy."""

    def resolve_knowledge(self, state: GameState) -> KnowledgeResolution:
        """村人p2を人狼と主張するprivate知識候補を返す."""
        del state
        return KnowledgeResolution(
            (
                KnowledgeClaim("p1", "knowledge", "p1", faction="werewolf"),
                KnowledgeClaim("p1", "knowledge", "p2", faction="werewolf"),
            )
        )


class InvalidKnowledgePolicy(SuppressDeathReactionPolicy):
    """設定と異なるdetailを返すfault policy."""

    def resolve_knowledge(self, state: GameState) -> KnowledgeResolution:
        """faction能力へroleを返す不正候補を生成する."""
        del state
        return KnowledgeResolution((KnowledgeClaim("p1", "knowledge", "p2", role="villager"),))


def _game_with_voting_policy(policy: VotingPolicy) -> Game:
    core = CoreRulePack().compile(_definition())
    rules = CompiledRuleSet(
        config=core.config,
        manifest=ExternalVictoryPack().manifest,
        ability_policy=core.ability_policy,
        voting_policy=policy,
        discussion_policy=core.discussion_policy,
        victory_policy=core.victory_policy,
    )
    game = Game.create(
        GameSetup(
            (
                Player("p1", "Alice"),
                Player("p2", "Bob"),
                Player("p3", "Carol"),
            )
        ),
        rules=rules,
        random=random.Random(7),
    )
    game.advance(random.Random(11))
    for action in (
        Action.vote("p1", "p2", reason="test"),
        Action.vote("p2", "p1", reason="test"),
        Action.vote("p3", "p1", reason="test"),
    ):
        game.submit(action)
    return game


def _game_with_ability_policy(policy: AbilityPolicy) -> Game:
    definition = RuleSetDefinition(
        player_count=3,
        role_counts={"villager": 2, "werewolf": 1},
        discussion=DiscussionConfig(),
        voting=VotingConfig(),
        night=NightConfig(),
        lifecycle=LifecycleConfig(starting_phase="night"),
        roles=RoleCatalog(
            {
                "villager": RoleDefinition("village", "village", ("immunity",)),
                "werewolf": RoleDefinition("werewolf", "werewolf", ("attack",)),
            }
        ),
        abilities={
            "attack": AbilityDefinition(
                kind="attack",
                phase=Phase.NIGHT,
                target_policy="other_alive_non_faction",
                start_day=1,
                max_uses=None,
                result_visibility="none",
                resolution_priority=100,
                allow_repeat_target=True,
                enabled_first_night=True,
                result_detail=None,
                knowledge_mode=None,
                tie_resolution="no_action",
                source_kinds=(),
            ),
            "immunity": AbilityDefinition(
                kind="immunity",
                phase=Phase.NIGHT,
                target_policy="none",
                start_day=1,
                max_uses=1,
                result_visibility="none",
                resolution_priority=100,
                allow_repeat_target=True,
                enabled_first_night=True,
                result_detail=None,
                knowledge_mode=None,
                tie_resolution=None,
                source_kinds=("attack",),
            ),
        },
    )
    core = CoreRulePack().compile(definition)
    rules = CompiledRuleSet(
        config=core.config,
        manifest=ExternalVictoryPack().manifest,
        ability_policy=policy,
        voting_policy=core.voting_policy,
        discussion_policy=core.discussion_policy,
        victory_policy=core.victory_policy,
    )
    game = Game.create(
        GameSetup(
            (
                Player("p1", "Wolf", "werewolf"),
                Player("p2", "Alice", "villager"),
                Player("p3", "Bob", "villager"),
            )
        ),
        rules=rules,
        random=random.Random(7),
    )
    game.submit(Action.use_ability("p1", "attack", "p2"))
    return game


def _game_with_death_reaction_policy(
    policy_factory: type[SuppressDeathReactionPolicy],
) -> Game:
    definition = RuleSetDefinition(
        player_count=4,
        role_counts={"hunter": 1, "villager": 2, "werewolf": 1},
        discussion=DiscussionConfig(),
        voting=VotingConfig(),
        night=NightConfig(),
        lifecycle=LifecycleConfig(
            starting_phase="day_discussion",
            require_all_actions_before_advance=False,
        ),
        roles=RoleCatalog(
            {
                "hunter": RoleDefinition("village", "village", ("reaction",)),
                "villager": RoleDefinition("village", "village"),
                "werewolf": RoleDefinition("werewolf", "werewolf"),
            }
        ),
        abilities={
            "reaction": AbilityDefinition(
                kind="death_reaction",
                phase=Phase.VOTING,
                target_policy="none",
                start_day=1,
                max_uses=1,
                result_visibility="none",
                resolution_priority=100,
                allow_repeat_target=True,
                enabled_first_night=True,
                result_detail=None,
                knowledge_mode=None,
                tie_resolution=None,
                source_kinds=(),
            )
        },
    )
    core = CoreRulePack().compile(definition)
    rules = CompiledRuleSet(
        config=core.config,
        manifest=ExternalVictoryPack().manifest,
        ability_policy=policy_factory(core.ability_policy),
        voting_policy=core.voting_policy,
        discussion_policy=core.discussion_policy,
        victory_policy=core.victory_policy,
    )
    game = Game.create(
        GameSetup(
            (
                Player("p1", "Wolf", "werewolf"),
                Player("p2", "Hunter", "hunter"),
                Player("p3", "Alice", "villager"),
                Player("p4", "Bob", "villager"),
            )
        ),
        rules=rules,
        random=random.Random(7),
    )
    game.advance(random.Random(11))
    for action in (
        Action.vote("p1", "p2", reason="test"),
        Action.vote("p2", "p1", reason="test"),
        Action.vote("p3", "p2", reason="test"),
        Action.vote("p4", "p2", reason="test"),
    ):
        game.submit(action)
    return game


def _game_with_knowledge_policy(
    policy_factory: type[SuppressDeathReactionPolicy],
) -> Game:
    definition = RuleSetDefinition(
        player_count=3,
        role_counts={"seer": 1, "villager": 1, "werewolf": 1},
        discussion=DiscussionConfig(),
        voting=VotingConfig(),
        night=NightConfig(),
        lifecycle=LifecycleConfig(starting_phase="night"),
        roles=RoleCatalog(
            {
                "seer": RoleDefinition("village", "village", ("knowledge",)),
                "villager": RoleDefinition("village", "village"),
                "werewolf": RoleDefinition("werewolf", "werewolf"),
            }
        ),
        abilities={
            "knowledge": AbilityDefinition(
                kind="knowledge",
                phase=Phase.NIGHT,
                target_policy="none",
                start_day=1,
                max_uses=None,
                result_visibility="private",
                resolution_priority=100,
                allow_repeat_target=True,
                enabled_first_night=True,
                result_detail="faction",
                knowledge_mode="allies",
                tie_resolution=None,
                source_kinds=(),
            )
        },
    )
    core = CoreRulePack().compile(definition)
    rules = CompiledRuleSet(
        config=core.config,
        manifest=ExternalVictoryPack().manifest,
        ability_policy=policy_factory(core.ability_policy),
        voting_policy=core.voting_policy,
        discussion_policy=core.discussion_policy,
        victory_policy=core.victory_policy,
    )
    return Game.create(
        GameSetup(
            (
                Player("p1", "Seer", "seer"),
                Player("p2", "Alice", "villager"),
                Player("p3", "Wolf", "werewolf"),
            )
        ),
        rules=rules,
        random=random.Random(7),
    )


def test_external_provider_is_used_only_after_explicit_registration() -> None:
    provider = ExternalVictoryPack()
    registry = RulePolicyRegistry((CoreRulePack(), provider))

    assert registry.provider_ids == ("core", "external-victory")
    assert registry.require("external-victory") is provider
    with pytest.raises(ValueError, match="unknown rule pack provider"):
        registry.require("not-registered")
    with pytest.raises(ValueError, match="duplicate rule pack provider"):
        RulePolicyRegistry((provider, provider))


def test_registry_compiles_only_the_registered_manifest() -> None:
    """Providerとcompile結果のidentity不一致を一局へ固定する前に拒否する."""
    provider = ExternalVictoryPack()
    registry = RulePolicyRegistry((provider,))
    definition = _definition()

    rules = registry.compile(provider.manifest.provider_id, definition)

    assert rules.manifest == provider.manifest
    with pytest.raises(ValueError, match="persisted manifest"):
        registry.compile(
            provider.manifest.provider_id,
            definition,
            expected_manifest=RulePackManifest(
                provider_id=provider.manifest.provider_id,
                contract_version=RULE_PACK_CONTRACT_VERSION,
                implementation_version="different",
                fingerprint=provider.manifest.fingerprint,
            ),
        )


def test_rule_pack_manifest_mapping_rejects_coerced_identity_values() -> None:
    """永続化したidentityの欠損や型違いを文字列へ黙って変換しない."""
    manifest = ExternalVictoryPack().manifest

    assert RulePackManifest.from_mapping(manifest.to_mapping()) == manifest
    invalid: dict[str, object] = manifest.to_mapping()
    invalid["fingerprint"] = 1
    with pytest.raises(ValueError, match="fingerprint must be a string"):
        RulePackManifest.from_mapping(invalid)
    invalid["fingerprint"] = "not-a-digest"
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        RulePackManifest.from_mapping(invalid)


def test_external_victory_policy_changes_outcome_without_mutating_state() -> None:
    rules = ExternalVictoryPack().compile(_definition())
    game = Game.create(
        GameSetup(
            (
                Player("p1", "Alice"),
                Player("p2", "Bob"),
                Player("p3", "Carol"),
            )
        ),
        rules=rules,
        random=random.Random(7),
    )

    events = game.advance(random.Random(11))

    assert game.snapshot().winner_id == "village"
    assert game.snapshot().win_result is not None
    assert game.snapshot().win_result.reason == "external_test_condition"
    assert events[-1].event_type == "game_finished"


def test_invalid_external_outcome_is_rejected_atomically() -> None:
    core = CoreRulePack().compile(_definition())
    rules = CompiledRuleSet(
        config=core.config,
        manifest=ExternalVictoryPack().manifest,
        ability_policy=core.ability_policy,
        voting_policy=core.voting_policy,
        discussion_policy=core.discussion_policy,
        victory_policy=InvalidVictoryPolicy(),
    )
    game = Game.create(
        GameSetup(
            (
                Player("p1", "Alice"),
                Player("p2", "Bob"),
                Player("p3", "Carol"),
            )
        ),
        rules=rules,
        random=random.Random(7),
    )
    before = game.snapshot()

    with pytest.raises(ValueError, match="winning player ids"):
        game.advance(random.Random(11))

    assert game.snapshot() is before


def test_external_voting_policy_changes_resolution_without_mutating_directly() -> None:
    game = _game_with_voting_policy(RedirectVotingPolicy())

    events = game.advance(random.Random(13))

    assert not game.snapshot().players["p2"].is_alive
    result = game.snapshot().history.votes[-1]
    assert result.eliminated_player_id == "p2"
    assert result.tie_break_policy == "external_redirect"
    assert next(event for event in events if event.event_type == "vote_resolved")


def test_invalid_voting_outcome_is_rejected_atomically() -> None:
    game = _game_with_voting_policy(InvalidVotingPolicy())
    before = game.snapshot()
    random_source = random.Random(13)
    random_state = random_source.getstate()

    with pytest.raises(ValueError, match="eliminated player must be alive"):
        game.advance(random_source)

    assert game.snapshot() is before
    assert random_source.getstate() == random_state


def test_discussion_policy_cannot_skip_response_after_opening() -> None:
    """外部Policyが構造化議論の必須responseを省略してもstateを変更しない."""
    core = CoreRulePack().compile(_definition())
    rules = CompiledRuleSet(
        config=core.config,
        manifest=core.manifest,
        ability_policy=core.ability_policy,
        voting_policy=core.voting_policy,
        discussion_policy=SkipResponseDiscussionPolicy(),
        victory_policy=core.victory_policy,
    )
    game = Game.create(
        GameSetup((Player("p1", "Alice"), Player("p2", "Bob"), Player("p3", "Carol"))),
        rules=rules,
        random=random.Random(7),
    )
    actor_id = next(
        player_id
        for player_id in game.snapshot().players
        if game.view_for(player_id).available_actions
    )
    subject_id = next(
        player.id
        for player in game.snapshot().players.values()
        if player.id != actor_id and player.is_alive
    )
    game.submit(
        Action.speech(
            actor_id,
            "意見を述べます。",
            speech_act="question",
            subject_id=subject_id,
        )
    )
    before = game.snapshot()

    with pytest.raises(ValueError, match="cannot complete"):
        game.advance(random.Random(11))

    assert game.snapshot() is before


def test_discussion_policy_cannot_start_outside_first_opening() -> None:
    """外部Policyも初回openingと全生存者を省略できない."""
    core = CoreRulePack().compile(_definition())
    rules = CompiledRuleSet(
        config=core.config,
        manifest=core.manifest,
        ability_policy=core.ability_policy,
        voting_policy=core.voting_policy,
        discussion_policy=InvalidStartDiscussionPolicy(),
        victory_policy=core.victory_policy,
    )

    random_source = random.Random(7)
    random_state = random_source.getstate()

    with pytest.raises(ValueError, match="first opening"):
        Game.create(
            GameSetup((Player("p1", "Alice"), Player("p2", "Bob"), Player("p3", "Carol"))),
            rules=rules,
            random=random_source,
        )

    assert random_source.getstate() == random_state


def test_response_must_advance_another_players_opening() -> None:
    """responseは自己反復と再質問を許可せず、他者のopeningへ前進回答する。"""
    game = Game.create(
        GameSetup((Player("p1", "Alice"), Player("p2", "Bob"), Player("p3", "Carol"))),
        rules=CoreRulePack().compile(_definition()),
        random=random.Random(7),
    )
    opening = game.snapshot().pending_actions.discussion_round
    assert opening is not None
    for actor_id in opening.actor_order:
        subject_id = next(item for item in opening.actor_order if item != actor_id)
        game.submit(
            Action.speech(
                actor_id,
                "判断材料を確認します。",
                speech_act="question",
                subject_id=subject_id,
            )
        )
    game.advance(random.Random(11))
    response = game.snapshot().pending_actions.discussion_round
    assert response is not None
    actor_id = response.current_actor_id
    speeches = {speech.speech_id: speech for speech in game.snapshot().history.speeches}
    own_reference = next(
        reference_id
        for reference_id in response.reference_ids
        if speeches[reference_id].player_id == actor_id
    )
    other_reference = next(
        reference_id
        for reference_id in response.reference_ids
        if speeches[reference_id].player_id != actor_id
    )
    subject_id = next(item for item in response.actor_order if item != actor_id)

    with pytest.raises(GameError, match="another player's speech"):
        game.submit(
            Action.speech(
                actor_id,
                "自分の問いを繰り返します。",
                speech_act="answer",
                subject_id=subject_id,
                evidence_id=own_reference,
                response_to_id=own_reference,
            )
        )
    with pytest.raises(GameError, match="act is not supported"):
        game.submit(
            Action.speech(
                actor_id,
                "別の問いを重ねます。",
                speech_act="question",
                subject_id=subject_id,
                evidence_id=other_reference,
                response_to_id=other_reference,
            )
        )
    with pytest.raises(GameError, match="contribute new content"):
        game.submit(
            Action.speech(
                actor_id,
                speeches[other_reference].message,
                speech_act="answer",
                subject_id=subject_id,
                evidence_id=other_reference,
                response_to_id=other_reference,
            )
        )


def test_discussion_round_rejects_duplicate_reference_ids() -> None:
    """応答候補を集合比較で曖昧にしない."""
    with pytest.raises(ValueError, match="unique speeches"):
        DiscussionRound(
            "response-1",
            1,
            DiscussionRoundKind.RESPONSE,
            "ordered",
            ("p1", "p2"),
            reference_ids=("speech-1", "speech-1"),
        )
    with pytest.raises(ValueError, match="cursor is outside"):
        DiscussionRound(
            "response-1",
            1,
            DiscussionRoundKind.RESPONSE,
            "ordered",
            ("p1", "p2"),
            cursor=2,
            reference_ids=("speech-1",),
        )


def test_external_ability_policy_changes_night_resolution_without_mutating_directly() -> None:
    game = _game_with_ability_policy(RedirectAbilityPolicy())

    events = game.advance(random.Random(13))

    assert game.snapshot().players["p2"].is_alive
    assert not game.snapshot().players["p3"].is_alive
    assert game.snapshot().history.nights[-1].attacked_player_id == "p2"
    assert events[0].event_type == "night_resolved"


def test_invalid_ability_outcome_is_rejected_atomically() -> None:
    game = _game_with_ability_policy(InvalidAbilityPolicy())
    before = game.snapshot()
    random_source = random.Random(13)
    random_state = random_source.getstate()

    with pytest.raises(GameError, match="Unknown player id"):
        game.advance(random_source)

    assert game.snapshot() is before
    assert random_source.getstate() == random_state


def test_ability_outcome_cannot_exceed_passive_use_limit() -> None:
    game = _game_with_ability_policy(ExcessPassiveUsePolicy())
    before = game.snapshot()

    with pytest.raises(ValueError, match="exceeds max uses"):
        game.advance(random.Random(13))

    assert game.snapshot() is before


def test_external_ability_policy_can_suppress_death_reaction() -> None:
    game = _game_with_death_reaction_policy(SuppressDeathReactionPolicy)

    game.advance(random.Random(13))

    assert not game.snapshot().players["p2"].is_alive
    assert all(game.snapshot().players[player_id].is_alive for player_id in ("p1", "p3", "p4"))
    assert game.snapshot().ability_uses.get("p2", {}).get("reaction", 0) == 0


def test_invalid_death_reaction_outcome_is_rejected_atomically() -> None:
    game = _game_with_death_reaction_policy(InvalidDeathReactionPolicy)
    before = game.snapshot()
    random_source = random.Random(13)
    random_state = random_source.getstate()

    with pytest.raises(ValueError, match="owner must already be dead"):
        game.advance(random_source)

    assert game.snapshot() is before
    assert random_source.getstate() == random_state


def test_external_knowledge_policy_changes_private_claim_without_leaking() -> None:
    game = _game_with_knowledge_policy(RedirectKnowledgePolicy)

    assert game.view_for("p1").known_factions["p2"] == "werewolf"
    assert game.view_for("p1").known_factions["p1"] == "village"
    assert "p2" not in game.view_for("p3").known_factions


def test_invalid_knowledge_outcome_is_rejected() -> None:
    game = _game_with_knowledge_policy(InvalidKnowledgePolicy)

    with pytest.raises(ValueError, match="faction knowledge"):
        game.view_for("p1")
