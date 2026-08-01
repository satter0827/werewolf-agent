from dataclasses import replace

from werewolf_agent.domain import (
    RULE_PACK_CONTRACT_VERSION,
    CompiledRuleSet,
    CoreRulePack,
    DiscussionConfig,
    GameSetup,
    LifecycleConfig,
    NightConfig,
    Player,
    RoleCatalog,
    RoleDefinition,
    RulePackManifest,
    RuleSetDefinition,
    VotingConfig,
    assert_rule_pack_contract,
)


class ExternalRulePack:
    @property
    def manifest(self) -> RulePackManifest:
        return RulePackManifest(
            provider_id="external-example",
            contract_version=RULE_PACK_CONTRACT_VERSION,
            implementation_version="1.0.0",
            fingerprint="1" * 64,
        )

    def compile(self, definition: RuleSetDefinition) -> CompiledRuleSet:
        compiled = CoreRulePack().compile(definition)
        return replace(compiled, manifest=self.manifest)


definition = RuleSetDefinition(
    player_count=4,
    role_counts={"werewolf": 1, "villager": 3},
    discussion=DiscussionConfig(cycles_per_day=1),
    voting=VotingConfig(),
    night=NightConfig(),
    lifecycle=LifecycleConfig(starting_phase="day_discussion"),
    roles=RoleCatalog(
        {
            "werewolf": RoleDefinition("werewolf", "werewolf"),
            "villager": RoleDefinition("village", "village"),
        }
    ),
    abilities={},
)
setup = GameSetup(tuple(Player(f"player-{index}", f"Player {index}") for index in range(1, 5)))

assert_rule_pack_contract(ExternalRulePack(), definition=definition, setup=setup)
