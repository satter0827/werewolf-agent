"""生成contract検査gate。"""

import os
import shutil
import sys
import time
from pathlib import Path

from scripts._infra.process import REPOSITORY_ROOT, CommandResult, run_command
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
            artifacts=("contracts/openapi.json", "contracts/api.ts"),
            diagnostics=("contracts/openapi.json", "contracts/api.ts"),
        )
    ]


def check_openapi_contract(context: RunContext, _: Path) -> CommandResult:
    """OpenAPIと生成したTypeScript型をtracked契約と比較する。"""
    started = time.monotonic()
    generated = context.run_dir / "contracts" / "openapi.json"
    generated_types = context.run_dir / "contracts" / "api.ts"
    command = [sys.executable, "-m", "scripts.contracts", "--output", str(generated)]
    result = run_command(
        command,
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
    )
    if result.returncode != 0:
        return result
    frontend_directory = REPOSITORY_ROOT / "frontend"
    npm = shutil.which("npm") or "npm"
    type_command = [
        npm,
        "exec",
        "--offline",
        "--",
        "openapi-typescript",
        os.path.relpath(generated, frontend_directory),
        "-o",
        os.path.relpath(generated_types, frontend_directory),
    ]
    type_result = run_command(
        type_command,
        cwd=frontend_directory,
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
    )
    if type_result.returncode != 0:
        return type_result
    expected = REPOSITORY_ROOT / "contracts" / "openapi.json"
    expected_types = REPOSITORY_ROOT / "frontend" / "src" / "generated" / "api.ts"
    matches = (
        expected.is_file()
        and expected_types.is_file()
        and generated.read_text(encoding="utf-8") == expected.read_text(encoding="utf-8")
        and generated_types.read_text(encoding="utf-8")
        == expected_types.read_text(encoding="utf-8")
    )
    output = result.output + type_result.output
    if not matches:
        output += "生成したOpenAPI契約またはTypeScript型がtracked契約と一致しません。\n"
    return CommandResult(
        command,
        0 if matches else 1,
        time.monotonic() - started,
        output,
    )


__all__ = ["GATES", "build", "check_openapi_contract"]
