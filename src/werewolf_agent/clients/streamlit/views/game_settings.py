"""Persistent game setup editor."""

from __future__ import annotations

import hashlib
import re
from typing import Any, cast

from pydantic import ValidationError

from werewolf_agent.clients.presentation import implements_features
from werewolf_agent.clients.streamlit.constants import SETUP_DRAFT_KEY
from werewolf_agent.clients.streamlit.i18n import I18nCatalog, Language
from werewolf_agent.clients.streamlit.operations import (
    create_saved_setup,
    create_setup_revision,
    list_saved_setups,
    list_setup_revisions,
    load_saved_setup,
    load_session,
    load_setup_catalog,
    load_setup_template,
    validate_setup,
)
from werewolf_agent.clients.streamlit.views.errors import render_app_error
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.api import SetupCreateRequest, SetupRevisionCreateRequest
from werewolf_agent.contracts.schemas import GameSetupDocumentRequest
from werewolf_agent.settings import AppSettings

_SOURCE_KEY = "werewolf_setup_document_source_v2"
_REVISION_KEY = "werewolf_setup_document_revision_v2"
_SETUP_ID_KEY = "werewolf_setup_document_id_v2"

_ABILITY_KIND_LABELS = {
    "attack": "襲撃",
    "inspect": "調査",
    "protect": "保護",
    "eliminate": "直接排除",
    "knowledge": "初期知識",
    "death_reaction": "死亡時の反応",
    "immunity": "無効化",
    "vulnerability": "弱点",
}
_FACTION_LABELS = {"village": "村側", "werewolf": "人狼側", "fox": "妖狐側"}
_PHASE_LABELS = {
    "night": "夜",
    "day_discussion": "昼の議論",
    "voting": "投票",
    "finished": "ゲーム終了後",
}
_TARGET_LABELS = {
    "alive": "生存者全員",
    "other_alive": "自分以外の生存者",
    "other_alive_non_faction": "自分以外の別陣営の生存者",
}
_VISIBILITY_LABELS = {"private": "能力を持つ本人だけ", "public": "全員", "none": "表示しない"}
_ACTION_LABELS = {
    "speech": "発言",
    "vote": "投票",
    "use_ability": "能力を使う",
    "pass": "見送る",
}
_NARRATION_LABELS = {
    "game_started": "ゲーム開始",
    "phase_started": "時間帯の開始",
    "night_resolved": "夜の結果",
    "vote_resolved": "投票結果",
    "game_finished": "ゲーム終了",
}


@implements_features(
    "setup_catalog_get",
    "setup_template_get",
    "setup_list",
    "setup_create",
    "setup_get",
    "setup_revision_get",
    "setup_revision_list",
    "setup_revision_create",
    "setup_validate",
)
def _render_game_settings_screen(
    st: Any,
    *,
    settings: AppSettings,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Edit a complete v2 document and explicitly persist immutable revisions."""
    try:
        setup_catalog = load_setup_catalog(settings=settings)
        session = load_session(settings=settings)
        saved = [] if session.anonymous else list_saved_setups(settings=settings).items
    except AppError as exc:
        render_app_error(st, exc, lang=lang)
        return

    st.title("ゲーム設定")
    st.caption("世界観、役職と能力、プレイヤー生成、ルールを一つの設定として管理します。")
    sources = [f"template:{value}" for value in setup_catalog.template_order]
    revisions = {
        value.setup_id: list_setup_revisions(settings=settings, setup_id=value.setup_id)
        for value in saved
    }
    sources.extend(
        f"saved:{value.setup_id}:{revision.revision}"
        for value in saved
        for revision in revisions[value.setup_id]
    )
    source_labels = {
        **{
            f"template:{value}": f"同梱: {setup_catalog.templates[value]['name']}"
            for value in setup_catalog.template_order
        },
        **{
            f"saved:{value.setup_id}:{revision.revision}": (
                f"保存済み: {value.display_name} (第{revision.revision}版)"
            )
            for value in saved
            for revision in revisions[value.setup_id]
        },
    }
    source = st.selectbox(
        "編集元",
        sources,
        index=_source_index(st.session_state, sources),
        format_func=lambda value: source_labels[value],
    )
    if st.session_state.get(_SOURCE_KEY) != source:
        try:
            _load_source(st.session_state, settings, source)
        except AppError as exc:
            render_app_error(st, exc, lang=lang)
            return
    draft = cast(dict[str, Any], st.session_state[SETUP_DRAFT_KEY])

    editor, summary = st.columns([3, 2], gap="large")
    with editor:
        tabs = st.tabs(["世界観", "役職と能力", "プレイヤー生成", "ルール", "確認"])
        with tabs[0]:
            _edit_theme(st, draft)
        with tabs[1]:
            _edit_roles_and_abilities(st, draft, tuple(setup_catalog.ability_kinds))
        with tabs[2]:
            _edit_players(st, draft)
        with tabs[3]:
            _edit_rules(st, draft)
        with tabs[4]:
            _render_confirmation(st, settings, lang, draft)
    with summary:
        _render_summary(st, draft)
        if session.anonymous:
            st.info(
                "保存するにはログインしてください。編集内容はゲーム作成前の確認に利用できます。"
            )
        else:
            _render_save(st, settings, lang, draft)
    st.session_state[SETUP_DRAFT_KEY] = draft


def _source_index(state: Any, sources: list[str]) -> int:
    """Keep the loaded immutable revision selected when the catalog grows."""
    loaded_source = state.get(_SOURCE_KEY)
    return sources.index(loaded_source) if loaded_source in sources else 0


def _load_source(state: Any, settings: AppSettings, source: str) -> None:
    mode, identifier, *revision = source.split(":")
    if mode == "template":
        template = load_setup_template(settings=settings, template_id=identifier)
        document = template.document
        state[_SETUP_ID_KEY] = None
        state[_REVISION_KEY] = None
    else:
        saved = load_saved_setup(
            settings=settings,
            setup_id=identifier,
            revision=int(revision[0]),
        )
        document = saved.document
        state[_SETUP_ID_KEY] = saved.setup_id
        state[_REVISION_KEY] = saved.revision
    state[SETUP_DRAFT_KEY] = document.model_dump(mode="json")
    state[_SOURCE_KEY] = source


def _edit_theme(st: Any, draft: dict[str, Any]) -> None:
    theme = draft["theme"]
    theme["name"] = st.text_input("設定名", value=theme["name"])
    theme["summary"] = st.text_area("概要", value=theme["summary"])
    theme["premise"] = st.text_area("導入", value=theme["premise"], height=120)
    theme["narration_enabled"] = st.toggle(
        "ナレーションを表示する", value=theme["narration_enabled"]
    )
    with st.expander("用語と説明"):
        for role_id in draft["mechanics"]["roles"]:
            theme["role_names"][role_id] = st.text_input(
                f"役職名: {theme['role_names'][role_id]}",
                value=theme["role_names"][role_id],
                key=f"theme_role_name_{role_id}",
            )
            theme["role_objectives"][role_id] = st.text_area(
                f"{theme['role_names'][role_id]}の目的",
                value=theme["role_objectives"][role_id],
                key=f"theme_role_objective_{role_id}",
            )
            theme["role_descriptions"][role_id] = st.text_area(
                f"{theme['role_names'][role_id]}の説明",
                value=theme["role_descriptions"][role_id],
                key=f"theme_role_description_{role_id}",
            )
        for ability_id in draft["mechanics"]["abilities"]:
            theme["ability_names"][ability_id] = st.text_input(
                f"能力名: {theme['ability_names'][ability_id]}",
                value=theme["ability_names"][ability_id],
                key=f"theme_ability_name_{ability_id}",
            )
            theme["ability_descriptions"][ability_id] = st.text_area(
                f"{theme['ability_names'][ability_id]}の説明",
                value=theme["ability_descriptions"][ability_id],
                key=f"theme_ability_description_{ability_id}",
            )
        for field, heading in (
            ("faction_names", "陣営名"),
            ("action_names", "行動名"),
            ("phase_names", "phase名"),
        ):
            st.markdown(f"**{heading}**")
            for concept_id, label in list(theme[field].items()):
                theme[field][concept_id] = st.text_input(
                    _concept_label(field, concept_id),
                    value=label,
                    key=f"theme_{field}_{concept_id}",
                )
    with st.expander("ナレーションの文面"):
        st.caption("1行を1つの候補として扱います。")
        for event_id, templates in list(theme["narration"].items()):
            value = st.text_area(
                _NARRATION_LABELS.get(event_id, "追加のナレーション"),
                value="\n".join(templates),
                key=f"theme_narration_{event_id}",
            )
            theme["narration"][event_id] = [
                line.strip() for line in value.splitlines() if line.strip()
            ]


def _edit_roles_and_abilities(
    st: Any, draft: dict[str, Any], ability_kinds: tuple[str, ...]
) -> None:
    mechanics = draft["mechanics"]
    theme = draft["theme"]
    st.subheader("役職")
    for role_id, role in list(mechanics["roles"].items()):
        label = theme["role_names"][role_id]
        with st.expander(label, expanded=True):
            if st.button("この役職を削除", key=f"delete_role_{role_id}"):
                mechanics["roles"].pop(role_id)
                mechanics["role_counts"].pop(role_id, None)
                for field in ("role_names", "role_objectives", "role_descriptions"):
                    theme[field].pop(role_id, None)
                st.rerun()
            mechanics["role_counts"][role_id] = st.number_input(
                "人数", min_value=1, value=mechanics["role_counts"][role_id], key=f"count_{role_id}"
            )
            role["identity_faction"] = st.selectbox(
                "正体の陣営",
                ["village", "werewolf", "fox"],
                index=["village", "werewolf", "fox"].index(role["identity_faction"]),
                format_func=_FACTION_LABELS.get,
                key=f"identity_{role_id}",
            )
            role["victory_team"] = st.selectbox(
                "勝利判定の陣営",
                ["village", "werewolf", "fox"],
                index=["village", "werewolf", "fox"].index(role["victory_team"]),
                format_func=_FACTION_LABELS.get,
                key=f"victory_{role_id}",
            )
            role["abilities"] = st.multiselect(
                "能力",
                list(mechanics["abilities"]),
                default=role["abilities"],
                format_func=lambda value: theme["ability_names"][value],
                key=f"abilities_{role_id}",
            )
    with st.expander("役職を追加"):
        name = st.text_input("新しい役職名", key="new_role_name")
        if st.button("役職を追加する", disabled=not name.strip()):
            role_id = _generated_id("role", name, set(mechanics["roles"]))
            mechanics["roles"][role_id] = {
                "identity_faction": "village",
                "victory_team": "village",
                "abilities": [],
            }
            mechanics["role_counts"][role_id] = 1
            theme["role_names"][role_id] = name.strip()
            theme["role_objectives"][role_id] = "陣営の勝利条件を満たします。"
            theme["role_descriptions"][role_id] = "能力の組み合わせで振る舞う役職です。"
            st.rerun()

    used_factions = {
        str(role[field])
        for role in mechanics["roles"].values()
        for field in ("identity_faction", "victory_team")
    }
    theme["faction_names"] = {
        faction_id: theme["faction_names"].get(faction_id, faction_id)
        for faction_id in sorted(used_factions)
    }

    st.subheader("能力")
    for ability_id, ability in list(mechanics["abilities"].items()):
        label = theme["ability_names"][ability_id]
        with st.expander(label):
            if st.button("この能力を削除", key=f"delete_ability_{ability_id}"):
                mechanics["abilities"].pop(ability_id)
                theme["ability_names"].pop(ability_id, None)
                theme["ability_descriptions"].pop(ability_id, None)
                for role in mechanics["roles"].values():
                    role["abilities"] = [item for item in role["abilities"] if item != ability_id]
                st.rerun()
            kind = st.selectbox(
                "効果",
                list(ability_kinds),
                index=list(ability_kinds).index(ability["kind"]),
                format_func=_ABILITY_KIND_LABELS.get,
                key=f"kind_{ability_id}",
            )
            if kind != ability["kind"]:
                _change_ability_kind(ability, kind)
            active = kind in {"attack", "inspect", "protect", "eliminate"}
            if active:
                ability["phase"] = "night"
                target_policies = ["alive", "other_alive", "other_alive_non_faction"]
                ability["target_policy"] = st.selectbox(
                    "対象",
                    target_policies,
                    index=target_policies.index(ability["target_policy"]),
                    format_func=_TARGET_LABELS.get,
                    key=f"target_{ability_id}",
                )
            else:
                ability["target_policy"] = "none"
                if kind in {"immunity", "vulnerability"}:
                    ability["phase"] = "night"
                else:
                    phases = (
                        ["night", "voting"]
                        if kind == "death_reaction"
                        else ["night", "day_discussion", "voting", "finished"]
                    )
                    if ability["phase"] not in phases:
                        ability["phase"] = phases[0]
                    ability["phase"] = st.selectbox(
                        "適用する時間帯",
                        phases,
                        index=phases.index(ability["phase"]),
                        format_func=_PHASE_LABELS.get,
                        key=f"phase_{ability_id}",
                    )
            ability["start_day"] = st.number_input(
                "使用開始日", min_value=1, value=ability["start_day"], key=f"start_{ability_id}"
            )
            if kind == "knowledge":
                ability["max_uses"] = "unlimited"
            else:
                limited = st.toggle(
                    "使用回数を制限する",
                    value=ability["max_uses"] != "unlimited",
                    key=f"limited_{ability_id}",
                )
                ability["max_uses"] = (
                    st.number_input(
                        "使用回数",
                        min_value=1,
                        value=(ability["max_uses"] if isinstance(ability["max_uses"], int) else 1),
                        key=f"uses_{ability_id}",
                    )
                    if limited
                    else "unlimited"
                )
            if kind in {"inspect", "knowledge"}:
                visibility = ["private", "public", "none"]
                ability["result_visibility"] = st.selectbox(
                    "結果の公開範囲",
                    visibility,
                    index=visibility.index(ability["result_visibility"]),
                    format_func=_VISIBILITY_LABELS.get,
                    key=f"visibility_{ability_id}",
                )
            else:
                ability["result_visibility"] = "none"
            ability["resolution_priority"] = st.number_input(
                "解決優先度",
                min_value=0,
                max_value=1000,
                value=ability["resolution_priority"],
                key=f"priority_{ability_id}",
            )
            if active:
                ability["allow_repeat_target"] = st.toggle(
                    "前回と同じ対象を許可する",
                    value=ability["allow_repeat_target"],
                    key=f"repeat_{ability_id}",
                )
            else:
                ability["allow_repeat_target"] = True
            if ability["phase"] == "night":
                ability["enabled_first_night"] = st.toggle(
                    "最初の夜から有効にする",
                    value=ability["enabled_first_night"],
                    key=f"first_night_{ability_id}",
                )
            else:
                ability["enabled_first_night"] = True
            if kind == "attack":
                tie_resolutions = ["random_target", "no_action"]
                ability["tie_resolution"] = st.selectbox(
                    "対象が同数の場合",
                    tie_resolutions,
                    index=tie_resolutions.index(ability["tie_resolution"]),
                    format_func={
                        "random_target": "抽選で決める",
                        "no_action": "効果なしにする",
                    }.get,
                    key=f"tie_{ability_id}",
                )
            if kind in {"inspect", "knowledge"}:
                details = ["faction", "role"]
                ability["result_detail"] = st.selectbox(
                    "得られる情報",
                    details,
                    index=details.index(ability["result_detail"]),
                    format_func={"faction": "陣営", "role": "役職"}.get,
                    key=f"detail_{ability_id}",
                )
            if kind == "knowledge":
                ability["knowledge_mode"] = st.selectbox(
                    "知識の内容",
                    ["allies", "last_eliminated"],
                    index=["allies", "last_eliminated"].index(
                        ability.get("knowledge_mode") or "allies"
                    ),
                    format_func={
                        "allies": "同じ陣営の仲間",
                        "last_eliminated": "直前に追放された人",
                    }.get,
                    key=f"knowledge_{ability_id}",
                )
            if kind in {"immunity", "vulnerability"}:
                source_options = (
                    ["attack", "eliminate", "inspect"] if kind == "immunity" else ["inspect"]
                )
                selected_sources = [
                    item for item in ability.get("source_kinds", []) if item in source_options
                ]
                if not selected_sources:
                    selected_sources = list(source_options)
                ability["source_kinds"] = st.multiselect(
                    "影響する効果",
                    source_options,
                    default=selected_sources,
                    format_func=_ABILITY_KIND_LABELS.get,
                    key=f"sources_{ability_id}",
                )
    with st.expander("能力を追加"):
        name = st.text_input("新しい能力名", key="new_ability_name")
        kind = st.selectbox(
            "効果",
            list(ability_kinds),
            format_func=_ABILITY_KIND_LABELS.get,
            key="new_ability_kind",
        )
        if st.button("能力を追加する", disabled=not name.strip()):
            ability_id = _generated_id("ability", name, set(mechanics["abilities"]))
            mechanics["abilities"][ability_id] = _new_ability(kind)
            theme["ability_names"][ability_id] = name.strip()
            theme["ability_descriptions"][ability_id] = "設定した条件で効果を解決します。"
            st.rerun()


def _edit_players(st: Any, draft: dict[str, Any]) -> None:
    generation = draft["player_generation"]
    st.caption("名前は重複させず、性格と作戦は再現可能な抽選で偏りを抑えて割り当てます。")
    generation["identities"] = st.data_editor(
        generation["identities"],
        num_rows="dynamic",
        width="stretch",
        column_config={
            "name": "名前",
            "age_min": "年齢の下限",
            "age_max": "年齢の上限",
            "gender": "性別表現",
        },
        key="identities",
    )
    generation["public_personas"] = st.data_editor(
        generation["public_personas"],
        num_rows="dynamic",
        width="stretch",
        column_config={"personality": "性格", "speaking_style": "話し方"},
        key="public_personas",
    )
    generation["private_strategies"] = st.data_editor(
        generation["private_strategies"],
        num_rows="dynamic",
        width="stretch",
        column_config={
            "reasoning_style": "推理方針",
            "risk_tolerance": "大胆さ",
            "evidence_focus": "重視する情報",
        },
        key="private_strategies",
    )


def _edit_rules(st: Any, draft: dict[str, Any]) -> None:
    rules = draft["mechanics"]["rules"]
    rules["day_speech_limit_per_player"] = st.number_input(
        "1日あたりの発言回数", min_value=0, value=rules["day_speech_limit_per_player"]
    )
    for key, label in (
        ("allow_self_vote", "自分への投票を許可する"),
        ("allow_vote_revision", "投票の変更を許可する"),
        ("allow_night_action_revision", "夜の行動変更を許可する"),
        ("reveal_role_on_death", "死亡時に役職を公開する"),
        ("require_all_actions_before_advance", "全員の行動後に進行する"),
    ):
        rules[key] = st.toggle(label, value=rules[key], key=f"rule_{key}")
    rules["starting_phase"] = st.selectbox(
        "開始する時間帯",
        ["night", "day_discussion"],
        index=["night", "day_discussion"].index(rules["starting_phase"]),
        format_func=_PHASE_LABELS.get,
    )
    rules["vote_tie_resolution"] = st.selectbox(
        "同票時の処理",
        ["no_elimination", "random_elimination", "revote"],
        index=["no_elimination", "random_elimination", "revote"].index(
            rules["vote_tie_resolution"]
        ),
        format_func={
            "no_elimination": "誰も追放しない",
            "random_elimination": "抽選で追放する",
            "revote": "再投票する",
        }.get,
    )


def _render_confirmation(
    st: Any,
    settings: AppSettings,
    lang: Language,
    draft: dict[str, Any],
) -> None:
    try:
        document = GameSetupDocumentRequest.model_validate(draft)
    except ValidationError as exc:
        st.error("設定を保存できる状態ではありません。")
        sections = "、".join(_validation_sections(exc))
        st.caption(f"{sections}に未入力、重複、または組み合わせできない内容があります。")
        return
    st.info("参照関係とゲーム進行条件をサーバーで確認できます。")
    if st.button("設定を検証する", width="stretch"):
        try:
            result = validate_setup(settings=settings, setup=document)
        except AppError as exc:
            render_app_error(st, exc, lang=lang)
            return
        st.success(f"{result.player_count}人でゲームを開始できる設定です。")


def _render_summary(st: Any, draft: dict[str, Any]) -> None:
    mechanics = draft["mechanics"]
    st.header("設定の要約")
    st.metric("プレイヤー", sum(mechanics["role_counts"].values()))
    left, right = st.columns(2)
    left.metric("役職", len(mechanics["roles"]))
    right.metric("能力", len(mechanics["abilities"]))
    st.caption(draft["theme"]["summary"])


def _render_save(
    st: Any,
    settings: AppSettings,
    lang: Language,
    draft: dict[str, Any],
) -> None:
    try:
        document = GameSetupDocumentRequest.model_validate(draft)
    except ValidationError:
        st.warning("入力内容を修正すると保存できます。")
        return
    setup_id = st.session_state.get(_SETUP_ID_KEY)
    revision = st.session_state.get(_REVISION_KEY)
    if setup_id is None:
        display_name = st.text_input("保存名", value=document.theme.name)
        if st.button("保存設定として複製", type="primary", width="stretch"):
            try:
                saved = create_saved_setup(
                    settings=settings,
                    request=SetupCreateRequest(display_name=display_name, document=document),
                )
            except AppError as exc:
                render_app_error(st, exc, lang=lang)
                return
            st.session_state[_SETUP_ID_KEY] = saved.setup_id
            st.session_state[_REVISION_KEY] = saved.revision
            st.success(f"第{saved.revision}版を保存しました。")
    elif st.button("新しい版として保存", type="primary", width="stretch"):
        try:
            saved = create_setup_revision(
                settings=settings,
                setup_id=str(setup_id),
                request=SetupRevisionCreateRequest(
                    expected_revision=int(revision), document=document
                ),
            )
        except AppError as exc:
            render_app_error(st, exc, lang=lang)
            return
        st.session_state[_REVISION_KEY] = saved.revision
        st.success(f"第{saved.revision}版を保存しました。")


def _validation_sections(error: ValidationError) -> tuple[str, ...]:
    labels = {
        "theme": "世界観",
        "mechanics": "役職と能力またはルール",
        "player_generation": "プレイヤー生成",
    }
    sections = {
        labels.get(str(item["loc"][0]), "確認")
        for item in error.errors(include_url=False)
        if item.get("loc")
    }
    return tuple(sorted(sections)) or ("確認",)


def _generated_id(prefix: str, name: str, existing: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    base = slug or hashlib.sha256(name.encode()).hexdigest()[:8]
    candidate = f"{prefix}_{base}"
    suffix = 2
    while candidate in existing:
        candidate = f"{prefix}_{base}_{suffix}"
        suffix += 1
    return candidate


def _concept_label(field: str, concept_id: str) -> str:
    if field == "faction_names":
        return _FACTION_LABELS.get(concept_id, "追加の陣営")
    if field == "action_names":
        return _ACTION_LABELS.get(concept_id, "追加の行動")
    return _PHASE_LABELS.get(concept_id, "追加の時間帯")


def _new_ability(kind: str) -> dict[str, Any]:
    passive_phase = "voting" if kind == "death_reaction" else "night"
    ability: dict[str, Any] = {
        "kind": kind,
        "phase": (
            "night" if kind in {"attack", "inspect", "protect", "eliminate"} else passive_phase
        ),
        "target_policy": (
            "other_alive" if kind in {"attack", "inspect", "protect", "eliminate"} else "none"
        ),
        "start_day": 1,
        "max_uses": "unlimited",
        "result_visibility": "private" if kind == "inspect" else "none",
        "resolution_priority": 100,
        "allow_repeat_target": True,
        "enabled_first_night": True,
    }
    if kind == "attack":
        ability["tie_resolution"] = "random_target"
    elif kind == "inspect":
        ability["result_detail"] = "faction"
    elif kind == "knowledge":
        ability["knowledge_mode"] = "allies"
        ability["result_detail"] = "faction"
    elif kind == "immunity":
        ability["source_kinds"] = ["attack", "eliminate", "inspect"]
    elif kind == "vulnerability":
        ability["source_kinds"] = ["inspect"]
    return ability


def _change_ability_kind(ability: dict[str, Any], kind: str) -> None:
    preserved = {
        key: ability[key]
        for key in (
            "start_day",
            "max_uses",
            "resolution_priority",
            "allow_repeat_target",
            "enabled_first_night",
        )
        if key in ability
    }
    replacement = _new_ability(kind)
    for key in (
        "phase",
        "target_policy",
        "result_visibility",
        "tie_resolution",
        "result_detail",
        "knowledge_mode",
        "source_kinds",
    ):
        ability.pop(key, None)
    ability.update(replacement)
    ability.update(preserved)


__all__ = ["_render_game_settings_screen"]
