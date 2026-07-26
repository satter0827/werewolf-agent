"""Browser E2E gate。"""

import sys
from pathlib import Path

from scripts._infra.process import CommandResult
from scripts.browser.e2e import run_e2e
from scripts.quality.models import Gate, RunContext

GATES = ("e2e",)


def build() -> list[Gate]:
    """Browser E2Eの依存・排他resource・成果物契約を返す。"""
    return [
        Gate(
            "e2e",
            "React and Streamlit Playwright E2E",
            (sys.executable, "-m", "scripts.browser"),
            action=run_browser_e2e,
            dependencies=("supabase-preflight",),
            exclusive_resources=("browser", "supabase"),
            artifacts=(
                "browser/results.json",
                "browser/html/index.html",
                "browser/contact-sheet.png",
                "browser/docker-before.json",
                "browser/docker-after.json",
                "browser/**/*.png",
            ),
        )
    ]


def run_browser_e2e(context: RunContext, _: Path) -> CommandResult:
    """React・Streamlit共通E2Eを実行する。"""
    return run_e2e(
        base_environment=context.environment,
        artifact_directory=context.run_dir / "browser",
        timeout_seconds=context.timeout_seconds,
        visual_regression=context.profile == "deep",
    )


__all__ = ["GATES", "build", "run_browser_e2e"]
