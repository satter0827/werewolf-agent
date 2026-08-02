import pytest
from pydantic import ValidationError

from werewolf_agent.application.models import GameRevealVote as ApplicationGameRevealVote
from werewolf_agent.contracts.schemas import (
    PLAYER_ACTION_REQUEST_ADAPTER,
    GameRevealVote,
    GameSetupSelectionRequest,
    SavedSetupRequest,
)


def test_saved_setup_selection_requires_an_explicit_revision() -> None:
    selection = SavedSetupRequest(mode="saved", setup_id="setup-1", revision=3)

    assert selection.revision == 3

    with pytest.raises(ValidationError):
        SavedSetupRequest.model_validate({"mode": "saved", "setup_id": "setup-1"})


def test_setup_selection_is_discriminated_by_mode() -> None:
    from pydantic import TypeAdapter

    selection = TypeAdapter(GameSetupSelectionRequest).validate_python(
        {"mode": "template", "template_id": "standard_6"}
    )

    assert selection.mode == "template"


def test_setup_wire_models_reject_unknown_fields() -> None:
    """未知fieldを無視してschema適合入力へ見せない。"""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        SavedSetupRequest.model_validate(
            {
                "mode": "saved",
                "setup_id": "setup-1",
                "revision": 3,
                "unknown": True,
            }
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "type": "speech",
            "utterance": "   ",
            "topic_id": "p2",
            "position": "support",
            "relation": "independent",
        },
        {
            "type": "speech",
            "utterance": "発言",
            "topic_id": " ",
            "position": "support",
            "relation": "independent",
        },
        {"type": "vote", "target_id": "p2", "reason": "\t"},
        {"type": "use_ability", "ability_id": " ", "target_id": None},
    ],
)
def test_player_action_wire_rejects_blank_structured_fields(payload: dict[str, object]) -> None:
    """空白だけのIDと文言を非同期command受付前に拒否する."""
    with pytest.raises(ValidationError):
        PLAYER_ACTION_REQUEST_ADAPTER.validate_python(payload)


@pytest.mark.parametrize("suffix", ["\u001c", "\u00a0", "\ufeff"])
def test_speech_action_wire_preserves_non_contract_whitespace(suffix: str) -> None:
    """HTTP境界で議論契約外のUnicode文字を表示文から除去しない."""
    utterance = f"Claim{suffix}"

    request = PLAYER_ACTION_REQUEST_ADAPTER.validate_python(
        {
            "type": "speech",
            "utterance": utterance,
            "topic_id": "p2",
            "position": "support",
            "relation": "independent",
        }
    )

    assert request.utterance == utterance


def test_reveal_vote_preserves_typed_evidence_links() -> None:
    application_vote = ApplicationGameRevealVote(
        day=1,
        votes={"p1": "p2"},
        reasons={"p1": "公開発言を根拠に判断"},
        evidence_ids={"p1": "speech:1:opening:p2"},
        counts={"p2": 1},
        tie_break_policy="none",
    )

    wire_vote = GameRevealVote.model_validate(application_vote.model_dump(mode="json"))

    assert wire_vote.evidence_ids == {"p1": "speech:1:opening:p2"}
