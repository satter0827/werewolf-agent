from werewolf_agent.domain import Action, ActionType

speech = Action.speech(
    player_id="player-1",
    message="占い結果を共有する。",
)

assert speech.type is ActionType.SPEECH
