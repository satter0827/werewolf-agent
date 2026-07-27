"""Streamlit画面の共通品質判定。"""

from __future__ import annotations

import re
from itertools import pairwise
from typing import Any

from playwright.sync_api import Page, expect

FORBIDDEN_INTERNAL_TERMS = re.compile(
    r"\b(?:MOC|mock|provider|model|token|Supabase|DB|API|Deploy)\b",
    re.I,
)


def assert_no_horizontal_overflow(page: Page) -> None:
    """Viewportからの横方向はみ出しを拒否する。"""
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert float(overflow) <= 1, f"horizontal overflow: {overflow}px"


def reset_streamlit_scroll(page: Page) -> None:
    """Streamlitの内部scroll領域を先頭へ戻して証跡の起点を揃える。"""
    page.evaluate(
        """() => {
          document.scrollingElement?.scrollTo(0, 0);
          document.querySelector('[data-testid="stMain"]')?.scrollTo(0, 0);
        }"""
    )


def assert_streamlit_quality(page: Page) -> None:
    """操作性、文書構造、accessibilityをまとめて検査する。"""
    from axe_playwright_python.sync_playwright import Axe  # type: ignore[import-untyped]

    expect(page.locator("body")).not_to_contain_text(FORBIDDEN_INTERNAL_TERMS, use_inner_text=True)
    assert_no_horizontal_overflow(page)
    undersized = page.locator("button:visible, [role=tab]:visible").evaluate_all(
        """nodes => nodes.map(node => ({
          height: node.getBoundingClientRect().height,
          text: (node.textContent || '').trim(),
          width: node.getBoundingClientRect().width
        })).filter(item => item.height < 44 || item.width < 44)"""
    )
    assert undersized == [], f"44px未満の操作対象があります: {undersized}"

    levels = page.locator(
        '[data-testid="stMain"] h1:visible, '
        '[data-testid="stMain"] h2:visible, '
        '[data-testid="stMain"] h3:visible'
    ).evaluate_all("nodes => nodes.map(node => Number(node.tagName.slice(1)))")
    assert levels and levels[0] == 1, f"最初のheadingがh1ではありません: {levels}"
    assert all(current - previous <= 1 for previous, current in pairwise(levels)), levels

    page.keyboard.press("Tab")
    expect(page.locator(":focus-visible")).to_be_visible()

    result = Axe().run(page)
    response = result.response
    violations = response.get("violations", []) if isinstance(response, dict) else []
    serious = [violation for violation in violations if _is_relevant_violation(violation)]
    assert serious == [], f"重大なAxe違反があります: {serious}"


def _is_relevant_violation(violation: Any) -> bool:
    if not isinstance(violation, dict) or violation.get("impact") not in {"critical", "serious"}:
        return False
    nodes = [
        node
        for node in violation.get("nodes", [])
        if isinstance(node, dict) and not _is_streamlit_number_step(node)
    ]
    if not nodes:
        return False
    sidebar_exception = violation.get("id") == "aria-allowed-attr" and all(
        ".stSidebar" in str(target) for node in nodes for target in node.get("target", [])
    )
    return not sidebar_exception


def _is_streamlit_number_step(node: dict[str, Any]) -> bool:
    """Streamlit標準number inputの既知の無名step buttonを識別する。"""
    return any(
        "stNumberInputStepDown" in str(target) or "stNumberInputStepUp" in str(target)
        for target in node.get("target", [])
    )


__all__ = [
    "assert_no_horizontal_overflow",
    "assert_streamlit_quality",
    "reset_streamlit_scroll",
]
