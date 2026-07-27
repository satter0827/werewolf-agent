from werewolf_agent.domain import Action, ActionType


def test_public_actions_do_not_accept_ability_ids() -> None:
    vote = Action(type=ActionType.VOTE, player_id="p1", target_id="p2")
    speech = Action(type=ActionType.SPEECH, player_id="p1", message="確認します。")

    assert vote.ability_id is None
    assert speech.ability_id is None
