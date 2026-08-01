from hashlib import sha256

from werewolf_agent.agents import RandomLegalAgentFactory
from werewolf_agent.domain import RULE_PACK_CONTRACT_VERSION, RulePackManifest
from werewolf_agent.experiments import (
    AgentBinding,
    ExperimentSpec,
    RotationMode,
    RulesCondition,
    plan_trials,
)

digest = lambda value: sha256(value.encode()).hexdigest()  # noqa: E731
agents = tuple(
    AgentBinding(controller_id, persona_id, RandomLegalAgentFactory().spec)
    for controller_id in ("c1", "c2", "c3")
    for persona_id in ("calm", "bold", "careful")
)
conditions = tuple(
    RulesCondition(
        condition_id,
        digest(f"setup:{condition_id}"),
        RulePackManifest(condition_id, RULE_PACK_CONTRACT_VERSION, "1.0.0", digest(condition_id)),
        ("villager", "seer", "werewolf"),
        agents,
    )
    for condition_id in ("baseline", "candidate")
)
spec = ExperimentSpec(
    "rules-comparison",
    conditions,
    (42,),
    ("p1", "p2", "p3"),
    ("c1", "c2", "c3"),
    ("calm", "bold", "careful"),
    RotationMode.NONE,
)

plans = plan_trials(spec)
assert plans[0].pair_id == plans[1].pair_id
