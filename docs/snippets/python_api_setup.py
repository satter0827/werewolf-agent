from werewolf_agent.setup import (
    PlayerGenerationDefinition,
    PlayerIdentityDefinition,
    PrivateStrategyDefinition,
    PublicPersonaDefinition,
    generate_players,
)

generation = PlayerGenerationDefinition(
    identities=(PlayerIdentityDefinition("Alice", 20, 30, "female"),),
    public_personas=(PublicPersonaDefinition("calm", "brief"),),
    private_strategies=(PrivateStrategyDefinition("analytic", "low", "claims"),),
)

first = generate_players(generation, player_count=1, seed=41)
second = generate_players(generation, player_count=1, seed=41)
assert first == second
