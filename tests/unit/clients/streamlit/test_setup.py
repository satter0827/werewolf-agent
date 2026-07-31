import pytest
from pydantic import ValidationError

from werewolf_agent.adapters.application_bridge import build_setup_catalog
from werewolf_agent.clients.streamlit.constants import SETUP_DRAFT_KEY
from werewolf_agent.clients.streamlit.views.game_settings import (
    _SOURCE_KEY,
    _new_ability,
    _source_index,
    _validation_sections,
)
from werewolf_agent.clients.streamlit.views.setup import (
    _inline_draft,
    _preview_fingerprint,
    _selection,
)
from werewolf_agent.contracts.schemas import GameSetupDocumentRequest


def test_setup_selection_keeps_saved_revision() -> None:
    selection = _selection("saved:setup-id:4")

    assert selection.mode == "saved"
    assert selection.revision == 4


def test_preview_fingerprint_changes_with_seed_or_revision() -> None:
    first = _selection("saved:setup-id:1")
    second = _selection("saved:setup-id:2")

    assert _preview_fingerprint(first, 7) != _preview_fingerprint(first, 8)
    assert _preview_fingerprint(first, 7) != _preview_fingerprint(second, 7)


def test_inline_editor_draft_reaches_game_creation_selection() -> None:
    document = build_setup_catalog().require_document("standard_6")
    inline_document = _inline_draft({SETUP_DRAFT_KEY: document.to_mapping()})

    selection = _selection("inline:draft", inline_document=inline_document)

    assert selection.mode == "inline"
    assert selection.document == inline_document


def test_new_passive_abilities_start_with_executable_conditions() -> None:
    immunity = _new_ability("immunity")
    vulnerability = _new_ability("vulnerability")
    death_reaction = _new_ability("death_reaction")

    assert immunity["phase"] == "night"
    assert immunity["source_kinds"] == ["attack", "eliminate", "inspect"]
    assert vulnerability["phase"] == "night"
    assert vulnerability["source_kinds"] == ["inspect"]
    assert death_reaction["phase"] == "voting"


def test_editor_validation_reports_beginner_facing_sections() -> None:
    payload = build_setup_catalog().require_document("standard_6").to_mapping()
    del payload["player_generation"]["public_personas"][0]["personality"]

    with pytest.raises(ValidationError) as raised:
        GameSetupDocumentRequest.model_validate(payload)

    assert _validation_sections(raised.value) == ("プレイヤー生成",)


def test_editor_keeps_loaded_revision_when_a_new_revision_appears() -> None:
    selected = "saved:setup-id:1"
    state = {_SOURCE_KEY: selected}
    sources = ["template:standard_6", selected, "saved:setup-id:2"]

    assert _source_index(state, sources) == 1
