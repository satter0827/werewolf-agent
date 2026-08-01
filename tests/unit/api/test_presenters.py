"""Application resultから独立したHTTP wire contractへの変換を検証する。"""

from datetime import UTC, datetime

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.api.presenters import observation_response, saved_setup_revision_response
from werewolf_agent.application import PlayerObservationResult, SavedSetupRevision


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
                    {"type": "vote", "ability_id": None},
                ],
                "legal_targets": {
                    "speech": [],
                    "use_ability:inspect": ["p2"],
                    "vote": ["p2"],
                },
                "legal_evidence": {
                    "speech": [],
                    "use_ability:inspect": [],
                    "vote": [
                        {
                            "evidence_id": "speech:1:round-1:p2",
                            "kind": "discussion",
                            "actor_id": "p2",
                            "topic_id": "p1",
                            "position": "undecided",
                        }
                    ],
                },
                "action_text_limits": {"speech": 180, "vote": 75},
                "discussion_round": {
                    "round_id": "round-2",
                    "cycle": 1,
                    "kind": "response",
                    "submission_mode": "ordered",
                    "actor_order": ["p1", "p2"],
                    "cursor": 0,
                    "reference_ids": ["speech:1:round-1:p2"],
                },
                "allowed_discussion_relations": ["support"],
                "history": {
                    "speeches": [
                        {
                            "day": 1,
                            "speech_id": "speech:1:round-1:p2",
                            "round_id": "round-1",
                            "round_kind": "opening",
                            "player_id": "p2",
                            "utterance": "公開発言",
                            "reason": "公開しない内部理由",
                            "topic_id": "p1",
                            "position": "undecided",
                            "relation": "independent",
                            "evidence_id": None,
                            "response_to_id": None,
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
        ),
        api_text_max_chars=100,
    )

    assert [item.key for item in response.observation.available_actions] == [
        "speech",
        "use_ability:inspect",
        "vote",
    ]
    assert response.observation.available_actions[0].message_required is True
    assert response.observation.available_actions[0].message_max_chars == 100
    assert response.observation.available_actions[1].legal_target_ids == ["p2"]
    assert response.observation.available_actions[2].evidence_options[0].actor_id == "p2"
    assert response.observation.available_actions[2].reason_max_chars == 75
    assert response.observation.discussion_round is not None
    assert response.observation.discussion_round.allowed_relations == ["support"]
    assert [
        item.model_dump() for item in response.observation.discussion_round.response_options
    ] == [
        {
            "response_to_id": "speech:1:round-1:p2",
            "evidence_id": "speech:1:round-1:p2",
            "topic_id": "p1",
            "position": "undecided",
            "relation": "support",
        }
    ]
    payload = response.model_dump(mode="json")
    assert "legal_targets" not in payload["observation"]
    assert "reason" not in payload["observation"]["history"]["speeches"][0]
    assert "nights" not in payload["observation"]["history"]
    assert "winning_player_ids" not in payload["observation"]["win_result"]


def test_saved_setup_presenter_serializes_immutable_document() -> None:
    document = build_setup_catalog().require_document("standard_6")
    response = saved_setup_revision_response(
        SavedSetupRevision(
            setup_id="setup-1",
            display_name="標準設定",
            revision=1,
            document=document,
            setup_checksum="setup-checksum",
            mechanics_checksum="mechanics-checksum",
            created_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
    )

    payload = response.model_dump(mode="json")

    assert payload["setup_id"] == "setup-1"
    assert payload["document"] == document.to_mapping()
