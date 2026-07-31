"""Streamlit主要導線のリリース前Browser検査。"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path

import httpx
from playwright.sync_api import Locator, Page, expect

from scripts.browser.scenarios.api import (
    add_setup_revision,
    create_authenticated_user,
    create_completed_game,
    create_saved_setup,
)
from scripts.browser.scenarios.quality import (
    assert_no_horizontal_overflow,
    assert_streamlit_quality,
    reset_streamlit_scroll,
    scroll_streamlit_to_text,
)


def test_setup_sections_and_validation(
    page: Page,
    streamlit_url: str,
    capture_public_screenshot: Callable[[Page, str], Path],
    device_name: str,
) -> None:
    page.goto(streamlit_url)
    expect(page.get_by_text("Werewolf Agent", exact=True)).to_be_visible()
    _open_navigation(page, "ゲーム設定")
    expect(page.get_by_role("heading", name="ゲーム設定")).to_be_visible()
    _close_sidebar_if_needed(page)
    for name in ("世界観", "役職と能力", "プレイヤー生成", "ルール", "確認"):
        tab = page.get_by_role("tab", name=name)
        expect(tab).to_be_visible()
        tab.click()
        expect(tab).to_have_attribute("aria-selected", "true")
    page.get_by_role("tab", name="確認").click()
    page.get_by_role("button", name="設定を検証する").click()
    expect(page.get_by_text("参照関係とゲーム進行条件をサーバーで確認できます。")).to_be_visible()
    assert_streamlit_quality(page)
    capture_public_screenshot(
        page,
        f"streamlit-setup-validation-{device_name}.png",
    )


def test_gameplay_waiting_speech_and_target(
    page: Page,
    streamlit_url: str,
    capture_public_screenshot: Callable[[Page, str], Path],
    device_name: str,
) -> None:
    page.goto(streamlit_url)
    expect(page.get_by_role("heading", name="ゲームを始める")).to_be_visible()
    page.get_by_role("textbox", name="再現用の番号").fill("6")
    page.get_by_role("button", name="プレイヤーを生成").click()
    expect(page.get_by_role("heading", name="生成されたプレイヤー")).to_be_visible()
    page.get_by_role("button", name="この内容でゲームを作成").click()
    expect(page.get_by_role("heading", name="月明かりの卓")).to_be_visible(timeout=30_000)
    expect(page.get_by_text("ゲーム卓", exact=True)).to_be_visible()
    expect(page.locator(".wa-status")).to_have_count(6)
    expect(page.locator(".wa-seat")).to_have_count(6)
    advance = page.get_by_role("button", name="1ステップ進める")
    expect(advance).to_be_visible(timeout=30_000)
    _capture_state(page, capture_public_screenshot, f"streamlit-gameplay-waiting-{device_name}.png")
    advance.focus()
    page.keyboard.press("Enter")
    expect(
        page.get_by_text("自動進行中です。入力が必要になったら停止します。").first
    ).to_be_visible(timeout=30_000)
    message = page.get_by_label("発言内容")
    expect(message).to_be_visible(timeout=30_000)
    capture_public_screenshot(page, f"streamlit-gameplay-speech-{device_name}.png")
    message.fill("公開情報を整理して話します。")
    message.press("Tab")
    submit = page.get_by_role("button", name="入力を送信")
    expect(submit).to_be_enabled()
    submit.click()
    target = page.get_by_label("対象を選ぶ")
    expect(target).to_be_visible(timeout=30_000)
    assert_streamlit_quality(page)
    capture_public_screenshot(page, f"streamlit-gameplay-target-{device_name}.png")
    page.context.set_offline(True)
    page.wait_for_timeout(1_000)
    page.context.set_offline(False)
    expect(page.get_by_role("heading", name="月明かりの卓")).to_be_visible(timeout=30_000)
    expect(page.get_by_label("対象を選ぶ")).to_be_visible(timeout=30_000)
    assert_streamlit_quality(page)
    capture_public_screenshot(page, f"streamlit-reconnected-{device_name}.png")


def test_completed_game_presents_result_before_timeline(
    page: Page,
    api_client: httpx.Client,
    streamlit_url: str,
    capture_public_screenshot: Callable[[Page, str], Path],
    device_name: str,
) -> None:
    api_url = os.environ.get("PLAYWRIGHT_API_URL", "http://api:8000")
    email, password, token = create_authenticated_user(
        api_client,
        os.environ["PLAYWRIGHT_SUPABASE_URL"],
        os.environ["PLAYWRIGHT_SUPABASE_PUBLISHABLE_KEY"],
    )
    create_completed_game(api_client, api_url, token)
    page.goto(streamlit_url)
    _sign_in(page, email=email, password=password)
    _open_navigation(page, "記録")
    expect(page.get_by_role("heading", name="ゲーム記録")).to_be_visible(timeout=30_000)
    _close_sidebar_if_needed(page)
    record = page.get_by_role("button", name="記録を開く", exact=True)
    expect(record).to_be_visible(timeout=30_000)
    _capture_state(
        page,
        capture_public_screenshot,
        f"streamlit-records-populated-{device_name}.png",
    )
    record.focus()
    page.keyboard.press("Enter")
    result = page.get_by_text("結果サマリー", exact=True)
    expect(result).to_be_visible(timeout=30_000)
    result_box = result.bounding_box()
    timeline_box = page.get_by_text("公開タイムライン", exact=True).first.bounding_box()
    assert result_box is not None and timeline_box is not None
    assert result_box["y"] < timeline_box["y"]
    expect(page.get_by_role("button", name="1ステップ進める")).to_have_count(0)
    assert_streamlit_quality(page)
    _capture_state(
        page,
        capture_public_screenshot,
        f"streamlit-gameplay-complete-{device_name}.png",
    )


def test_setup_revision_conflict_explains_reload(
    page: Page,
    api_client: httpx.Client,
    streamlit_url: str,
    capture_public_screenshot: Callable[[Page, str], Path],
    device_name: str,
) -> None:
    """画面外で更新されたsetupを上書きせず、再読込の案内を表示する。"""
    api_url = os.environ.get("PLAYWRIGHT_API_URL", "http://api:8000")
    email, password, token = create_authenticated_user(
        api_client,
        os.environ["PLAYWRIGHT_SUPABASE_URL"],
        os.environ["PLAYWRIGHT_SUPABASE_PUBLISHABLE_KEY"],
    )
    setup_id, document = create_saved_setup(
        api_client,
        api_url,
        token,
        display_name="競合確認",
    )
    page.goto(streamlit_url)
    _sign_in(page, email=email, password=password)
    _open_navigation(page, "ゲーム設定")
    expect(page.get_by_role("heading", name="ゲーム設定")).to_be_visible(timeout=30_000)
    _close_sidebar_if_needed(page)
    _select_streamlit_option(page, "編集元", "保存済み: 競合確認 (第1版)")
    save = page.get_by_role("button", name="新しい版として保存")
    expect(save).to_be_visible(timeout=30_000)
    add_setup_revision(
        api_client,
        api_url,
        token,
        setup_id=setup_id,
        expected_revision=1,
        document=document,
    )
    save.click()
    conflict_message = page.get_by_text("別の操作で新しい設定版が保存されています。")
    expect(conflict_message).to_be_visible(timeout=30_000)
    expect(page.get_by_text("必要な対応: 最新の状態を読み込み直してください。")).to_be_visible()
    _close_sidebar_if_needed(page)
    page.get_by_role("combobox", name=re.compile("編集元")).focus()
    assert_streamlit_quality(page)
    _close_sidebar_if_needed(page)
    scroll_streamlit_to_text(page, "別の操作で新しい設定版が保存されています。")
    capture_public_screenshot(page, f"streamlit-conflict-{device_name}.png")


def test_observer_uses_public_presentation(
    page: Page,
    streamlit_url: str,
    capture_public_screenshot: Callable[[Page, str], Path],
    device_name: str,
) -> None:
    page.goto(streamlit_url)
    _open_navigation(page, "観戦")
    expect(page.get_by_role("heading", name="ゲームを観戦")).to_be_visible()
    _close_sidebar_if_needed(page)
    page.get_by_role("button", name="プレイヤーを生成").click()
    expect(page.get_by_role("heading", name="生成されたプレイヤー")).to_be_visible()
    page.get_by_role("button", name="この内容でゲームを作成").click()
    expect(page.get_by_text("ゲーム卓", exact=True)).to_be_visible()
    expect(page.get_by_text("観戦モード", exact=True).first).to_be_visible()
    assert_streamlit_quality(page)
    _capture_state(page, capture_public_screenshot, f"streamlit-observer-{device_name}.png")


def test_records_settings_and_narrow_layout(
    page: Page,
    streamlit_url: str,
    capture_public_screenshot: Callable[[Page, str], Path],
    device_name: str,
) -> None:
    page.goto(streamlit_url)
    _open_navigation(page, "記録")
    expect(page.get_by_role("heading", name="ゲーム記録")).to_be_visible()
    expect(page.get_by_role("button", name="プレイを始める")).to_be_visible()
    expect(page.get_by_role("button", name="観戦を始める")).to_be_visible()
    _close_sidebar_if_needed(page)
    _capture_state(
        page,
        capture_public_screenshot,
        f"streamlit-records-empty-{device_name}.png",
    )
    _open_navigation(page, "表示設定")
    _close_sidebar_if_needed(page)
    expect(page.get_by_role("heading", name="表示設定")).to_be_visible()
    expect(page.get_by_role("combobox", name="言語")).to_be_visible()
    assert_streamlit_quality(page)
    _capture_state(page, capture_public_screenshot, f"streamlit-settings-{device_name}.png")
    if device_name == "desktop":
        page.set_viewport_size({"width": 320, "height": 844})
        assert_no_horizontal_overflow(page)
        _open_navigation(page, "プレイ")
        _close_sidebar_if_needed(page)
        expect(page.get_by_role("heading", name="ゲームを始める")).to_be_visible()
        assert_streamlit_quality(page)
        _capture_state(page, capture_public_screenshot, "streamlit-setup-narrow-320.png")


def test_degraded_shell_explains_recovery(
    page: Page,
    degraded_streamlit_url: str,
    capture_public_screenshot: Callable[[Page, str], Path],
    device_name: str,
) -> None:
    page.goto(degraded_streamlit_url)
    expect(page.get_by_text(re.compile(r"ログインを一時的に利用できません"))).to_be_visible(
        timeout=30_000
    )
    expect(page.get_by_text(re.compile(r"接続が復旧すると.*利用できます"))).to_be_visible()
    assert_streamlit_quality(page)
    _capture_state(page, capture_public_screenshot, f"streamlit-degraded-{device_name}.png")


def _open_navigation(page: Page, label: str) -> None:
    _open_sidebar_if_needed(page)
    button: Locator = page.get_by_role("button", name=label, exact=True).first
    button.focus()
    page.keyboard.press("Enter")


def _select_streamlit_option(page: Page, label: str, option: str) -> None:
    combobox = page.get_by_role("combobox", name=re.compile(label))
    combobox.click()
    choice = page.get_by_role("option", name=option, exact=True)
    expect(choice).to_be_visible()
    choice.click()


def _sign_in(page: Page, *, email: str, password: str) -> None:
    _open_sidebar_if_needed(page)
    login = page.locator('[data-testid="stExpander"] summary').filter(has_text="ログイン")
    login.focus()
    page.keyboard.press("Enter")
    page.get_by_label("メールアドレス").fill(email)
    page.get_by_label("パスワード").fill(password)
    button = page.get_by_role("button", name="ログイン", exact=True).last
    button.focus()
    page.keyboard.press("Enter")
    expect(page.get_by_text(email)).to_be_visible(timeout=30_000)


def _close_sidebar_if_needed(page: Page) -> None:
    button = page.get_by_role(
        "button", name=re.compile(r"close sidebar|keyboard_double_arrow_left", re.I)
    )
    if button.is_visible():
        button.focus()
        page.keyboard.press("Enter")


def _capture_state(
    page: Page,
    capture_public_screenshot: Callable[[Page, str], Path],
    filename: str,
) -> None:
    reset_streamlit_scroll(page)
    capture_public_screenshot(page, filename)


def _open_sidebar_if_needed(page: Page) -> None:
    button = page.get_by_role(
        "button", name=re.compile(r"open sidebar|keyboard_double_arrow_right", re.I)
    )
    if button.is_visible():
        button.click()
