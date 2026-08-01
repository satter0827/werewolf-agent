from werewolf_agent.domain import (
    Action,
    ActionType,
    DiscussionPosition,
    DiscussionRelation,
)

speech = Action.speech(
    player_id="player-1",
    utterance="占い結果を共有する。",
    topic_id="player-2",
    position=DiscussionPosition.SUPPORT,
    relation=DiscussionRelation.CHALLENGE,
    evidence_id="speech:d1:c1:opening:player-2",
    response_to_id="speech:d1:c1:opening:player-2",
)

assert speech.type is ActionType.SPEECH
