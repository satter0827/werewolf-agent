"""Python・Frontend test gate。"""

import os
import sys
import time
import xml.etree.ElementTree as ET
from functools import partial
from pathlib import Path

from scripts._infra.process import TEMPORARY_ROOT, CommandResult, run_command
from scripts.quality.models import Gate, QualitySettings, RunContext

UNIT_GATES = ("pytest", "vitest")
COVERAGE_GATES = ("coverage",)
DEEP_GATES = ("deep-tests", "deep-integration")
GATES = (*UNIT_GATES, *COVERAGE_GATES, *DEEP_GATES)


def build(
    run_dir: Path,
    settings: QualitySettings,
    jobs: int,
) -> list[Gate]:
    """pytestの選択規則と成果物契約を所有するtest gateを返す。"""
    python = sys.executable
    workers = max(1, min(4, jobs))
    basetemp = TEMPORARY_ROOT / "pytest" / f"{os.getpid()}-{time.time_ns()}"
    return [
        Gate(
            "pytest",
            "Python quick test",
            (
                python,
                "-m",
                "pytest",
                "--test-level=quick",
                "-n",
                str(workers),
                "--dist",
                "loadscope",
                "--benchmark-disable",
                "--junitxml",
                str(run_dir / "test-results" / "quick.xml"),
                "--json-report",
                "--json-report-file",
                str(run_dir / "test-results" / "quick.json"),
                "--html",
                str(run_dir / "test-results" / "quick.html"),
                "--self-contained-html",
                "--basetemp",
                str(basetemp),
                "tests",
            ),
            artifacts=(
                "test-results/quick.xml",
                "test-results/quick.json",
                "test-results/quick.html",
            ),
        ),
        Gate(
            "coverage",
            "Python total and branch coverage",
            tuple(coverage_command(run_dir, settings)),
            action=partial(run_coverage, settings=settings),
            artifacts=(
                "coverage/coverage.xml",
                "coverage/html/index.html",
                "test-results/coverage.xml",
                "test-results/coverage.json",
                "test-results/coverage.html",
            ),
        ),
        Gate(
            "deep-tests",
            "Failure injection and extended domain tests",
            (
                python,
                "-m",
                "pytest",
                "--test-level=deep",
                "--confirm-deep",
                "-m",
                "deep and not integration",
                "-n",
                "0",
                "--junitxml",
                str(run_dir / "test-results" / "deep.xml"),
                "--json-report",
                "--json-report-file",
                str(run_dir / "test-results" / "deep.json"),
                "--html",
                str(run_dir / "test-results" / "deep.html"),
                "--self-contained-html",
                "tests",
            ),
            artifacts=(
                "test-results/deep.xml",
                "test-results/deep.json",
                "test-results/deep.html",
            ),
        ),
        Gate(
            "deep-integration",
            "Extended Supabase concurrency tests",
            (
                python,
                "-m",
                "pytest",
                "--test-level=deep",
                "--confirm-deep",
                "-m",
                "deep and integration",
                "-n",
                "0",
                "--junitxml",
                str(run_dir / "test-results" / "deep-integration.xml"),
                "--json-report",
                "--json-report-file",
                str(run_dir / "test-results" / "deep-integration.json"),
                "--html",
                str(run_dir / "test-results" / "deep-integration.html"),
                "--self-contained-html",
                "tests",
            ),
            dependencies=("supabase-preflight",),
            exclusive_resources=("supabase",),
            artifacts=(
                "test-results/deep-integration.xml",
                "test-results/deep-integration.json",
                "test-results/deep-integration.html",
            ),
        ),
    ]


def run_coverage(
    context: RunContext,
    _: Path,
    *,
    settings: QualitySettings,
) -> CommandResult:
    """総合coverageとbranch rateを判定せず観測する。"""
    started = time.monotonic()
    command = coverage_command(context.run_dir, settings)
    coverage = run_command(
        command,
        timeout_seconds=context.timeout_seconds,
        environment=context.environment,
    )
    if coverage.returncode != 0:
        return coverage
    errors, branch_percentage = branch_coverage_contract(
        context.run_dir / "coverage" / "coverage.xml",
        minimum_percentage=0,
    )
    output = [coverage.output]
    if branch_percentage is not None:
        output.append(f"branch coverage: {branch_percentage:.2f}% (観測値)\n")
    if errors:
        output.append("branch coverage契約に違反しています:\n")
        output.extend(f"- {error}\n" for error in errors)
    return CommandResult(
        command,
        1 if errors else 0,
        time.monotonic() - started,
        "".join(output),
    )


def coverage_command(run_dir: Path, settings: QualitySettings) -> list[str]:
    """Coverage成果物を同じrunへ保存するpytest commandを返す。"""
    return [
        sys.executable,
        "-m",
        "pytest",
        "--test-level=check",
        "-m",
        "not benchmark",
        "--cov=werewolf_agent",
        "--cov-branch",
        "--cov-report",
        f"xml:{run_dir / 'coverage' / 'coverage.xml'}",
        "--cov-report",
        f"html:{run_dir / 'coverage' / 'html'}",
        "--cov-fail-under=0",
        "--junitxml",
        str(run_dir / "test-results" / "coverage.xml"),
        "--json-report",
        "--json-report-file",
        str(run_dir / "test-results" / "coverage.json"),
        "--html",
        str(run_dir / "test-results" / "coverage.html"),
        "--self-contained-html",
        "tests/unit",
    ]


def branch_coverage_contract(
    result_path: Path,
    *,
    minimum_percentage: int,
) -> tuple[list[str], float | None]:
    """Coverage XMLからbranch rateを読み、設定下限との違反を返す。"""
    try:
        root = ET.parse(result_path).getroot()
        rate = float(root.attrib["branch-rate"])
    except (ET.ParseError, KeyError, OSError, ValueError) as error:
        return [f"coverage XMLのbranch-rateを読み取れません: {error}"], None
    if not 0 <= rate <= 1:
        return [f"branch-rateが範囲外です: {rate}"], None
    percentage = rate * 100
    if percentage < minimum_percentage:
        return [
            f"branch coverage {percentage:.2f}% は下限 {minimum_percentage}% を下回っています。"
        ], percentage
    return [], percentage


__all__ = [
    "COVERAGE_GATES",
    "DEEP_GATES",
    "GATES",
    "UNIT_GATES",
    "branch_coverage_contract",
    "build",
    "coverage_command",
    "run_coverage",
]
