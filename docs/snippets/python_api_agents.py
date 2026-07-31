from werewolf_agent.agents import (
    AgentContext,
    AgentObservation,
    DecisionOption,
    DecisionRequest,
    ObservedPlayer,
    RandomLegalAgentFactory,
    assert_agent_factory_contract,
)


def request(session_id: str, player_id: str, target_id: str) -> DecisionRequest:
    context = AgentContext(session_id, "game-1", player_id, session_seed=11)
    me = ObservedPlayer(player_id, player_id, True)
    other = ObservedPlayer(target_id, target_id, True)
    return DecisionRequest(
        decision_id=f"decision-{session_id}",
        context=context,
        observation=AgentObservation("voting", 1, me, (me, other)),
        public_timeline=(),
        options=(DecisionOption("vote", legal_target_ids=(target_id,)),),
        decision_seed=17,
    )


factory = RandomLegalAgentFactory()
assert_agent_factory_contract(
    factory,
    requests=(
        request("session-1", "player-1", "player-2"),
        request("session-2", "player-2", "player-1"),
    ),
)
