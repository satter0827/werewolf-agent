"""品質結果の集約、成果物検証、人間向けsummary生成。"""

from __future__ import annotations

import json
import platform
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import TypedDict

from scripts._infra.process import redact_artifacts, utc_now, write_json
from scripts.quality.artifacts import (
    validate_references,
    validate_retention_capacity,
    write_manifest,
)
from scripts.quality.models import GateResult, RunContext, State
from scripts.versioning.versions import QUALITY_EVIDENCE_VERSION


class CoverageFileMetric(TypedDict):
    """ファイル単位のline coverage観測値。"""

    path: str
    line_percent: float
    covered: int
    valid: int
    missing: int


def write_summary(
    context: RunContext,
    results: list[GateResult],
) -> tuple[State, Path]:
    finished_at = utc_now()
    duration_seconds = (finished_at - context.started_at).total_seconds()
    report_path = context.run_dir / "report.json"
    metrics, artifact_issues = collect_run_metrics(context.run_dir)
    artifact_issues.extend(validate_references(context.run_dir, results))
    artifact_issues.extend(validate_retention_capacity(context.run_dir))
    if artifact_issues:
        artifact_result = GateResult(
            name="artifact-validation",
            description="Quality artifact validation",
            state="error",
            duration_seconds=0.0,
            message="; ".join(artifact_issues),
        )
        results.append(artifact_result)
        append_events(context.run_dir / "events.jsonl", [artifact_result])
    state = result_state(results)
    report = {
        "schema_version": QUALITY_EVIDENCE_VERSION,
        "run_id": context.run_id,
        "profile": context.profile,
        "selection": {
            "requested_profile": context.requested_profile or context.profile,
            "resolved_profile": context.profile,
            "reason": context.selection_reason,
        },
        "execution": {
            "revision": context.initial_repository_snapshot.revision
            if context.initial_repository_snapshot
            else None,
            "tree": context.initial_repository_snapshot.tree
            if context.initial_repository_snapshot
            else None,
        },
        "change": {
            "base_ref": context.change.base_ref,
            "base_revision": context.change.base_revision,
            "head_revision": context.change.head_revision or None,
            "merge_base_revision": context.change.merge_base_revision,
            "changed_paths": list(context.change.changed_paths),
        },
        "workspace": {
            "dirty": context.initial_repository_snapshot.dirty
            if context.initial_repository_snapshot
            else None,
            "fingerprint": context.initial_repository_snapshot.fingerprint
            if context.initial_repository_snapshot
            else None,
        },
        "state": state,
        "jobs": context.jobs,
        "started_at": context.started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": duration_seconds,
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "dependency_fingerprint": context.initial_dependency_fingerprint,
        },
        "metrics": metrics,
        "artifact_issues": artifact_issues,
        "artifact_manifest": "manifest.json",
        "results": [asdict(result) for result in results],
    }
    write_json(report_path, report)
    summary = [
        f"# 品質評価: {context.profile}",
        "",
        f"- 判定: `{state}`",
        f"- Run ID: `{context.run_id}`",
        f"- 選択: `{context.requested_profile or context.profile}` → `{context.profile}`",
        f"- 選定理由: {context.selection_reason or 'profileを明示指定しました。'}",
        f"- 実行revision: `{context.initial_repository_snapshot.revision}`"
        if context.initial_repository_snapshot
        else "- 実行revision: 取得できませんでした。",
        f"- 実行tree: `{context.initial_repository_snapshot.tree}`"
        if context.initial_repository_snapshot
        else "- 実行tree: 取得できませんでした。",
        f"- 変更path: `{len(context.change.changed_paths)}` 件",
        f"- 所要時間: `{duration_seconds:.2f}` 秒",
        "",
        "| Gate | 判定 | 秒 |",
        "| --- | --- | ---: |",
    ]
    summary.extend(
        f"| {result.description} | {result.state} | {result.duration_seconds:.2f} |"
        for result in results
    )
    summary.extend(_metric_summary(metrics, artifact_issues))
    problems = [result for result in results if result.state not in {"passed", "skipped"}]
    if problems:
        summary.extend(["", "## 調査対象", ""])
        for result in problems:
            detail = result.message or "詳細はログを確認してください。"
            log = f" (`{result.log}`)" if result.log else ""
            summary.append(f"- `{result.name}`: {detail}{log}")
    (context.run_dir / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    # manifestのhashは、秘密情報を除去した最終内容に対して計算する。
    redact_artifacts(context.run_dir)
    write_manifest(context.run_dir, results)
    return state, report_path


def result_state(results: Sequence[GateResult]) -> State:
    """Gate結果から最上位状態を一貫した優先順位で返す。"""
    if any(result.state == "error" for result in results):
        return "error"
    if any(result.state == "failed" for result in results):
        return "failed"
    if any(result.state == "blocked" for result in results):
        return "blocked"
    return "passed"


def collect_run_metrics(run_dir: Path) -> tuple[dict[str, object], list[str]]:
    """既存成果物からAIが直接比較できる指標を収集する。"""
    metrics: dict[str, object] = {"tests": {}, "browser_artifacts": []}
    issues: list[str] = []

    tests: dict[str, object] = {}
    for path in sorted((run_dir / "test-results").glob("*.xml")):
        try:
            all_suites = list(ET.parse(path).getroot().iter("testsuite"))
            suites = [
                suite
                for suite in all_suites
                if not any(child.tag == "testsuite" for child in suite)
            ]
            totals = {
                key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
                for key in ("tests", "failures", "errors", "skipped")
            }
            totals["passed"] = (
                totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
            )
            tests[path.stem] = totals
        except (ET.ParseError, OSError, ValueError) as error:
            issues.append(f"{path.name}を解析できません: {error}")
    metrics["tests"] = tests

    coverage_path = run_dir / "coverage" / "coverage.xml"
    if coverage_path.exists():
        try:
            coverage_root = ET.parse(coverage_path).getroot()
            coverage = coverage_root.attrib
            lines_valid = int(coverage["lines-valid"])
            lines_covered = int(coverage["lines-covered"])
            branches_valid = int(coverage["branches-valid"])
            branches_covered = int(coverage["branches-covered"])
            total_valid = lines_valid + branches_valid
            metrics["unit_coverage"] = {
                "total_percent": round(
                    (lines_covered + branches_covered) / total_valid * 100,
                    2,
                )
                if total_valid
                else 100.0,
                "line_percent": round(float(coverage["line-rate"]) * 100, 2),
                "branch_percent": round(float(coverage["branch-rate"]) * 100, 2),
                "lines": {"covered": lines_covered, "valid": lines_valid},
                "branches": {"covered": branches_covered, "valid": branches_valid},
                "lowest_files": _lowest_coverage_files(coverage_root),
            }
        except (ET.ParseError, KeyError, OSError, ValueError) as error:
            issues.append(f"coverage.xmlを解析できません: {error}")

    benchmark_path = run_dir / "benchmarks" / "core.json"
    if benchmark_path.exists():
        try:
            document = json.loads(benchmark_path.read_text(encoding="utf-8"))
            benchmarks = document["benchmarks"]
            if not isinstance(benchmarks, list):
                raise ValueError("benchmarksが配列ではありません。")
            metrics["benchmarks"] = [
                {
                    "name": benchmark["name"],
                    "mean_ms": round(float(benchmark["stats"]["mean"]) * 1000, 3),
                    "rounds": int(benchmark["stats"]["rounds"]),
                }
                for benchmark in benchmarks
            ]
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            issues.append(f"core.jsonを解析できません: {error}")

    browser_root = run_dir / "browser"
    metrics["browser_artifacts"] = [
        path.relative_to(run_dir).as_posix()
        for path in sorted(browser_root.rglob("*"))
        if path.is_file()
    ]
    return metrics, issues


def _lowest_coverage_files(root: ET.Element, *, limit: int = 10) -> list[CoverageFileMetric]:
    """未検証riskの優先順位を示す低line coverageファイルを返す。"""
    files: list[CoverageFileMetric] = []
    for class_element in root.iter("class"):
        filename = class_element.attrib.get("filename")
        if not filename:
            continue
        lines = list(class_element.iter("line"))
        if not lines:
            continue
        covered = sum(int(line.attrib.get("hits", "0")) > 0 for line in lines)
        valid = len(lines)
        files.append(
            {
                "path": filename.replace("\\", "/"),
                "line_percent": round(covered / valid * 100, 2),
                "covered": covered,
                "valid": valid,
                "missing": valid - covered,
            }
        )
    return sorted(
        files,
        key=lambda item: (
            -item["missing"],
            item["line_percent"],
            item["path"],
        ),
    )[:limit]


def _metric_summary(metrics: dict[str, object], artifact_issues: list[str]) -> list[str]:
    """構造化指標を人間向けsummaryへ変換する。"""
    summary = ["", "## 指標", ""]
    tests = metrics.get("tests")
    if isinstance(tests, dict):
        for name, value in tests.items():
            if isinstance(value, dict):
                summary.append(
                    f"- `{name}`: {value.get('passed', 0)} passed, "
                    f"{value.get('failures', 0)} failed, "
                    f"{value.get('errors', 0)} errors, "
                    f"{value.get('skipped', 0)} skipped"
                )
    coverage = metrics.get("unit_coverage")
    if isinstance(coverage, dict):
        summary.append(
            "- unit coverage: "
            f"total {coverage.get('total_percent')}%, "
            f"line {coverage.get('line_percent')}%, "
            f"branch {coverage.get('branch_percent')}%"
        )
        lowest_files = coverage.get("lowest_files")
        if isinstance(lowest_files, list) and lowest_files:
            summary.append("- coverage優先候補:")
            for item in lowest_files[:5]:
                if isinstance(item, dict):
                    summary.append(
                        f"  - `{item.get('path')}`: {item.get('line_percent')}% "
                        f"({item.get('covered')}/{item.get('valid')})"
                    )
    benchmarks = metrics.get("benchmarks")
    if isinstance(benchmarks, list):
        for benchmark in benchmarks:
            if isinstance(benchmark, dict):
                summary.append(
                    f"- benchmark `{benchmark.get('name')}`: "
                    f"mean {benchmark.get('mean_ms')}ms, "
                    f"{benchmark.get('rounds')} rounds"
                )
    browser_artifacts = metrics.get("browser_artifacts")
    if isinstance(browser_artifacts, list):
        summary.append(f"- browser artifacts: {len(browser_artifacts)} files")
    if artifact_issues:
        summary.extend(["", "### 成果物解析の問題", ""])
        summary.extend(f"- {issue}" for issue in artifact_issues)
    return summary


def append_events(event_path: Path, results: Sequence[GateResult]) -> None:
    """完了または省略したgateを追記可能なeventとして保存する。"""
    with event_path.open("a", encoding="utf-8") as events:
        for result in results:
            events.write(
                json.dumps(
                    {
                        "event": "gate_completed",
                        "gate": result.name,
                        "state": result.state,
                        "duration_seconds": result.duration_seconds,
                        "timestamp": utc_now().isoformat(),
                        "message": result.message,
                        "log": result.log,
                        "execution_origin": result.execution_origin,
                        "source_run": result.source_run,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


__all__ = [
    "append_events",
    "collect_run_metrics",
    "result_state",
    "write_summary",
]
