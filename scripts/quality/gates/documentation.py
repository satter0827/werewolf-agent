"""文書検査gate。"""

import json
import shutil
import sys
import time
from pathlib import Path

from scripts._infra.process import CommandResult, EnvironmentBlockedError
from scripts.docs import build_documentation
from scripts.quality.models import Gate, RunContext

GATES = ("docs",)


def build_documentation_gate(context: RunContext, _log_path: Path) -> CommandResult:
    """Docs buildを実行し、非成功時の構造化診断をrunへ退避する。"""
    command = (sys.executable, "-m", "scripts.docs", "build")
    started = time.monotonic()
    returncode, report_path = build_documentation()
    diagnostic = context.run_dir / "docs" / "report.json"
    if returncode != 0 and report_path.is_file():
        diagnostic.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(report_path, diagnostic)
    if returncode == 2:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        findings = report.get("findings", [])
        message = findings[0].get("message") if findings else "Docs buildの前提が不足しています。"
        raise EnvironmentBlockedError(str(message))
    return CommandResult(
        list(command),
        returncode,
        time.monotonic() - started,
        str(report_path),
    )


def build() -> list[Gate]:
    """独立したDocs公開moduleを呼ぶgateを返す。"""
    return [
        Gate(
            "docs",
            "Sphinx warning-as-error build",
            (sys.executable, "-m", "scripts.docs", "build"),
            action=build_documentation_gate,
            dependencies=("architecture",),
            artifacts=("outputs/docs/index.html", "outputs/docs/report.json"),
            diagnostics=("docs/report.json",),
        )
    ]


__all__ = ["GATES", "build", "build_documentation_gate"]
