"""Setup selection, deterministic roster preview, and game creation screen."""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from pydantic import ValidationError

from werewolf_agent.clients.presentation import implements_features
from werewolf_agent.clients.streamlit.constants import SETUP_DRAFT_KEY
from werewolf_agent.clients.streamlit.history import create_session_game_selection
from werewolf_agent.clients.streamlit.i18n import I18nCatalog, Language
from werewolf_agent.clients.streamlit.operations import (
    create_game_from_setup,
    list_saved_setups,
    list_setup_revisions,
    load_session,
    load_setup_catalog,
    preview_players,
)
from werewolf_agent.clients.streamlit.setup import VIEW_GAME, switch_view
from werewolf_agent.clients.streamlit.state import (
    clear_message,
    remember_active_game_selection,
    remember_selected_history,
)
from werewolf_agent.clients.streamlit.views.errors import render_app_error
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.schemas import (
    DeliberationLevel,
    GameSetupDocumentRequest,
    GameSetupSelectionRequest,
    InlineSetupRequest,
    SavedSetupRequest,
    TemplateSetupRequest,
)
from werewolf_agent.settings import AppSettings

_PREVIEW_KEY = "werewolf_setup_preview"
_PREVIEW_FINGERPRINT_KEY = "werewolf_setup_preview_fingerprint"


@implements_features(
    "game_create",
    "setup_catalog_get",
    "setup_template_get",
    "setup_player_preview",
    "setup_list",
    "setup_revision_list",
)
def _render_setup_screen(
    st: Any,
    *,
    settings: AppSettings,
    catalog: I18nCatalog,
    lang: Language,
    observer: bool,
    mutations_available: bool = True,
) -> None:
    """Render only the inputs needed to create a game from a complete setup."""
    try:
        setup_catalog = load_setup_catalog(settings=settings)
        session = load_session(settings=settings)
        saved = [] if session.anonymous else list_saved_setups(settings=settings).items
        revisions = {
            item.setup_id: list_setup_revisions(settings=settings, setup_id=item.setup_id)
            for item in saved
        }
    except AppError as exc:
        render_app_error(st, exc, lang=lang)
        return

    st.title("ゲームを観戦" if observer else "ゲームを始める")
    st.caption("設定、再現用の番号、参加する席を確認してからゲームを作成します。")
    choices = [f"template:{item}" for item in setup_catalog.template_order]
    choices.extend(
        f"saved:{item.setup_id}:{revision.revision}"
        for item in saved
        for revision in revisions[item.setup_id]
    )
    labels = {
        **{
            f"template:{template_id}": setup_catalog.templates[template_id]["name"]
            for template_id in setup_catalog.template_order
        },
        **{
            f"saved:{item.setup_id}:{revision.revision}": (
                f"{item.display_name} (第{revision.revision}版)"
            )
            for item in saved
            for revision in revisions[item.setup_id]
        },
    }
    inline_document = _inline_draft(st.session_state)
    if inline_document is not None:
        choices.append("inline:draft")
        labels["inline:draft"] = f"編集中: {inline_document.theme.name}"
    selected = st.selectbox(
        "ゲーム設定",
        choices,
        format_func=lambda value: labels[value],
        help="設定の編集と保存はサイドバーの「ゲーム設定」から行えます。",
    )
    seed_text = st.text_input(
        "再現用の番号",
        value="",
        help="空欄では自動的に決まります。同じ設定と番号からは同じプレイヤーが生成されます。",
    )
    try:
        seed = int(seed_text) if seed_text.strip() else None
    except ValueError:
        st.error("再現用の番号は整数で入力してください。")
        return
    selection = _selection(selected, inline_document=inline_document)
    fingerprint = _preview_fingerprint(selection, seed)
    if st.button("プレイヤーを生成", use_container_width=True):
        try:
            st.session_state[_PREVIEW_KEY] = preview_players(
                settings=settings,
                setup=selection,
                seed=seed,
            )
            st.session_state[_PREVIEW_FINGERPRINT_KEY] = fingerprint
        except AppError as exc:
            render_app_error(st, exc, lang=lang)

    preview = (
        st.session_state.get(_PREVIEW_KEY)
        if st.session_state.get(_PREVIEW_FINGERPRINT_KEY) == fingerprint
        else None
    )
    if preview is None:
        st.info("設定または再現用の番号を変更した場合は、プレイヤーを生成し直してください。")
        return

    st.subheader("生成されたプレイヤー")
    st.dataframe(
        [
            {
                "seat": player.player_id,
                "名前": player.name,
                "年齢": player.age,
                "性別表現": player.gender,
                "性格": player.personality,
                "話し方": player.speaking_style,
            }
            for player in preview.players
        ],
        use_container_width=True,
        hide_index=True,
    )
    manual_player_id = None
    if not observer:
        manual_player_id = st.selectbox(
            "参加する席",
            [player.player_id for player in preview.players],
            format_func=lambda player_id: next(
                f"{player.player_id}: {player.name}"
                for player in preview.players
                if player.player_id == player_id
            ),
        )
    level = cast(
        DeliberationLevel,
        st.selectbox(
            "エージェントの考慮時間",
            ["quick", "standard", "deep"],
            index=1,
            format_func={"quick": "短く", "standard": "標準", "deep": "深く"}.get,
        ),
    )
    st.caption(f"確定した再現用の番号: {preview.seed}")
    if not mutations_available:
        st.warning("現在はゲームを作成できません。しばらく待ってから再試行してください。")
        return
    if st.button("この内容でゲームを作成", type="primary", use_container_width=True):
        try:
            created = create_game_from_setup(
                settings=settings,
                setup=selection,
                seed=preview.seed,
                manual_player_id=manual_player_id,
                deliberation_level=level,
            )
        except AppError as exc:
            render_app_error(st, exc, lang=lang)
            return
        game_selection = create_session_game_selection(
            created,
            manual_player_id=manual_player_id,
            player_count=len(preview.players),
            seed=preview.seed,
            deliberation_level=level,
        )
        remember_active_game_selection(st.session_state, game_selection)
        remember_selected_history(st.session_state, f"session:{game_selection.selection_id}")
        clear_message(st.session_state)
        switch_view(st.session_state, VIEW_GAME)
        st.rerun()


def _selection(
    value: str,
    *,
    inline_document: GameSetupDocumentRequest | None = None,
) -> GameSetupSelectionRequest:
    mode, identifier, *revision = value.split(":")
    if mode == "template":
        return TemplateSetupRequest(mode="template", template_id=identifier)
    if mode == "inline":
        if inline_document is None:
            raise ValueError("inline setup draft is not available")
        return InlineSetupRequest(mode="inline", document=inline_document)
    return SavedSetupRequest(mode="saved", setup_id=identifier, revision=int(revision[0]))


def _inline_draft(state: Any) -> GameSetupDocumentRequest | None:
    value = state.get(SETUP_DRAFT_KEY)
    if value is None:
        return None
    try:
        return GameSetupDocumentRequest.model_validate(value)
    except ValidationError:
        return None


def _preview_fingerprint(selection: GameSetupSelectionRequest, seed: int | None) -> str:
    payload = json.dumps(
        {"setup": selection.model_dump(mode="json"), "seed": seed},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


__all__ = ["_render_setup_screen"]
