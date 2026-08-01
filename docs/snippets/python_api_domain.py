from werewolf_agent.domain import Action, ActionType

speech = Action.speech(
    player_id="player-1",
    message="占い結果を共有する。",
    speech_act="challenge",
    subject_id="player-2",
    evidence_id="speech:d1:c1:opening:player-2",
)

assert speech.type is ActionType.SPEECH
