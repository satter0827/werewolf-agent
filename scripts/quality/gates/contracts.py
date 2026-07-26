"""生成contract検査gate。"""

import shutil
import sys
import time
from pathlib import Path

from scripts._infra.process import (
    REPOSITORY_ROOT,
    CommandResult,
    EnvironmentBlockedError,
    run_command,
)
from scripts.quality.models import Gate, RunContext

GATES = ("openapi", "schemathesis")
DEEP_GATES = ("schemathesis-stateful",)


def build() -> list[Gate]:
    """Git管理するOpenAPI生成契約のgateを返す。"""
    return [
        Gate(
            "openapi",
            "Generated OpenAPI contract",
            (sys.executable, "-m", "scripts.contracts"),
            action=check_openapi_contract,
            dependencies=("environment",),
            exclusive_resources=("frontend-workspace",),
            artifacts=("contracts/openapi.json", "contracts/api.ts"),
            diagnostics=("contracts/openapi.json", "contracts/api.ts"),
        ),
        Gate(
            "schemathesis",
            "Generated API positive and negative contract cases",
            (
                sys.executable,
                "-m",
                "pytest",
                "--test-level=check",
                "--junitxml",
                "{run_dir}/test-results/schemathesis.xml",
                "--json-report",
                "--json-report-file",
                "{run_dir}/test-results/schemathesis.json",
                "--html",
                "{run_dir}/test-results/schemathesis.html",
                "--self-contained-html",
                "tests/contract",
            ),
            action=run_schemathesis,
            dependencies=("environment",),
            artifacts=(
                "test-results/schemathesis.xml",
                "test-results/schemathesis.json",
                "test-results/schemathesis.html",
            ),
        ),
        Gate(
            "schemathesis-stateful",
            "Long-running stateful API contract exploration",
            (
                sys.executable,
                "-m",
                "pytest",
                "--test-level=deep",
                "--confirm-deep",
                "--junitxml",
                "{run_dir}/test-results/schemathesis-stateful.xml",
                "--json-report",
                "--json-report-file",
                "{run_dir}/test-results/schemathesis-stateful.json",
                "--html",
                "{run_dir}/test-results/schemathesis-stateful.html",
                "--self-contained-html",
                "tests/contract/test_openapi_stateful.py",
            ),
            action=run_schemathesis,
            dependencies=("environment",),
            artifacts=(
                "test-results/schemathesis-stateful.xml",
                "test-results/schemathesis-stateful.json",
                "test-results/schemathesis-stateful.html",
            ),
        ),
    ]


def run_schemathesis(context: RunContext, log_path: Path) -> CommandResult:
    """Run固有pathへSchemathesisの人・AI向け結果を保存する。"""
    command = [
        part.replace("{run_dir}", str(context.run_dir))
        for part in next(gate for gate in build() if gate.name == log_path.stem).command
    ]
    return run_command(
        command,
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
    )


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
    node = shutil.which("node") or "node"
    cli = frontend_directory / "node_modules" / "openapi-typescript" / "bin" / "cli.js"
    if not cli.is_file():
        raise EnvironmentBlockedError(
            "lock済みのopenapi-typescriptがありません。環境準備を実行してください。"
        )
    type_command = [
        node,
        str(cli),
        str(generated),
        "-o",
        str(generated_types),
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


__all__ = ["DEEP_GATES", "GATES", "build", "check_openapi_contract", "run_schemathesis"]
