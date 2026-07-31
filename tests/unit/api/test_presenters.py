"""Application resultから独立したHTTP wire contractへの変換を検証する。"""

from werewolf_agent.api.presenters import observation_response
from werewolf_agent.application import PlayerObservationResult


def test_observation_presenter_exposes_typed_actions_without_private_fields() -> None:
    response = observation_response(
        PlayerObservationResult(
            game_id="game-1",
            player_id="p1",
            observation={
                "phase": "day_discussion",
                "day": 2,
                "me": {"id": "p1", "name": "P1", "status": "alive", "role": "seer"},
                "players": [
                    {"id": "p1", "name": "P1", "status": "alive", "role": "seer"},
                    {"id": "p2", "name": "P2", "status": "alive", "role": None},
                ],
                "known_roles": {"p1": "seer"},
                "known_factions": {"p1": "village"},
                "available_actions": [
                    {"type": "speech", "ability_id": None},
                    {"type": "use_ability", "ability_id": "inspect"},
                ],
                "legal_targets": {"speech": [], "use_ability:inspect": ["p2"]},
                "history": {
                    "speeches": [
                        {
                            "day": 1,
                            "player_id": "p2",
                            "message": "公開発言",
                            "reason": "公開しない内部理由",
                            "focus_id": None,
                            "evidence_id": None,
                        }
                    ],
                    "votes": [],
                    "nights": [{"private": "value"}],
                },
                "win_result": {
                    "winner": "village",
                    "reason": "werewolves_eliminated",
                    "day": 2,
                    "winning_player_ids": ["p1", "p2"],
                },
            },
        )
    )

    assert [item.key for item in response.observation.available_actions] == [
        "speech",
        "use_ability:inspect",
    ]
    assert response.observation.available_actions[0].message_required is True
    assert response.observation.available_actions[1].legal_target_ids == ["p2"]
    payload = response.model_dump(mode="json")
    assert "legal_targets" not in payload["observation"]
    assert "reason" not in payload["observation"]["history"]["speeches"][0]
    assert "nights" not in payload["observation"]["history"]
    assert "winning_player_ids" not in payload["observation"]["win_result"]
