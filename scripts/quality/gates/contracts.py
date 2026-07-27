"""生成contract検査gate。"""

import sys
import time
from pathlib import Path

from scripts._infra.process import (
    REPOSITORY_ROOT,
    CommandResult,
    run_command,
)
from scripts.quality.models import Gate, RunContext

GATES = ("openapi",)


def build() -> list[Gate]:
    """Git管理するOpenAPI生成契約のgateを返す。"""
    return [
        Gate(
            "openapi",
            "Generated OpenAPI contract",
            (sys.executable, "-m", "scripts.contracts"),
            action=check_openapi_contract,
            dependencies=("environment",),
            artifacts=("contracts/openapi.json",),
            diagnostics=("contracts/openapi.json",),
        )
    ]


def check_openapi_contract(context: RunContext, _: Path) -> CommandResult:
    """OpenAPIを生成してtracked契約と比較する。"""
    started = time.monotonic()
    generated = context.run_dir / "contracts" / "openapi.json"
    command = [sys.executable, "-m", "scripts.contracts", "--output", str(generated)]
    result = run_command(
        command,
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
    )
    if result.returncode != 0:
        return result
    expected = REPOSITORY_ROOT / "contracts" / "openapi.json"
    matches = expected.is_file() and generated.read_text(encoding="utf-8") == expected.read_text(
        encoding="utf-8"
    )
    output = result.output
    if not matches:
        output += "生成したOpenAPI契約がtracked契約と一致しません。\n"
    return CommandResult(
        command,
        0 if matches else 1,
        time.monotonic() - started,
        output,
    )


__all__ = ["GATES", "build", "check_openapi_contract"]
