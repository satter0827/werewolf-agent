from werewolf_agent.agents import RandomLegalAgentFactory
from werewolf_agent.simulation import PlayerController, SimulationSpec

controllers = {
    "player-1": PlayerController("player-1", RandomLegalAgentFactory()),
    "player-2": PlayerController("player-2", RandomLegalAgentFactory()),
}
spec = SimulationSpec("trial-1", "game-1", 42, controllers)

# session = SimulationRunner().start(game, spec)
assert tuple(spec.controllers) == ("player-1", "player-2")
