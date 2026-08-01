from types import SimpleNamespace

from werewolf_agent.clients.streamlit.history import SessionGameSelection
from werewolf_agent.clients.streamlit.i18n import load_i18n
from werewolf_agent.clients.streamlit.views.history import _record_label
from werewolf_agent.settings import AppSettings


def test_session_selection_contains_only_runtime_choices() -> None:
    selection = SessionGameSelection(
        selection_id="selection",
        game_id="game",
        manual_player_id="p1",
        player_count=6,
        seed=7,
        deliberation_level="standard",
    )

    assert selection.manual_player_id == "p1"
    assert not hasattr(selection, "custom_roles")
    assert not hasattr(selection, "character_assignments")


def test_record_label_is_localized_without_internal_game_id() -> None:
    catalog = load_i18n(AppSettings(_env_file=None))
    game = SimpleNamespace(game_id="internal-uuid", status="completed", day=3)

    label = _record_label(game, index=2, catalog=catalog, lang="ja")

    assert label == "ゲーム 2 / 終了 / 3日目"
    assert game.game_id not in label
