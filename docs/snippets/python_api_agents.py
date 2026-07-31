from werewolf_agent.agents import (
    AgentContext,
    AgentObservation,
    DecisionOption,
    DecisionRequest,
    ObservedPlayer,
    RandomLegalAgentFactory,
)

context = AgentContext("session-1", "game-1", "player-1", session_seed=11)
me = ObservedPlayer("player-1", "Alice", True)
other = ObservedPlayer("player-2", "Bob", True)
request = DecisionRequest(
    decision_id="decision-1",
    context=context,
    observation=AgentObservation("voting", 1, me, (me, other)),
    public_timeline=(),
    options=(DecisionOption("vote", legal_target_ids=("player-2",)),),
    decision_seed=17,
)

factory = RandomLegalAgentFactory()
first = factory.create(context)
second = factory.create(context)
assert first is not second
assert first.decide(request) == second.decide(request)
first.close()
second.close()
