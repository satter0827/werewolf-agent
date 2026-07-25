"""品質runnerの公開仕様を検査する。"""

from __future__ import annotations

import json
import tarfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from scripts.quality import runner as quality
from scripts.quality.gates import distribution

ROOT = Path(__file__).resolve().parents[3]


def _write_contract_sdist(path: Path) -> None:
    """pyproject.tomlの公開source契約を満たす最小sdistを作る。"""
    with tarfile.open(path, mode="w:gz") as archive:
        for source in distribution.sdist_contract():
            repository_path = ROOT / source
            member = (
                f"package/{source}"
                if repository_path.is_file()
                else f"package/{source}/contract-placeholder"
            )
            info = tarfile.TarInfo(member)
            content = b"contract"
            info.size = len(content)
            archive.addfile(info, BytesIO(content))


def test_profile_commands_write_machine_readable_results_to_run_directory(
    tmp_path: Path,
) -> None:
    """pytest、coverage、benchmarkの成果物を同じrunへ関連付ける。"""

    commands = [
        argument
        for stage in quality._profile_stages("deep", 1, tmp_path)
        for gate in stage
        for argument in gate.command
    ]
    settings = quality.load_quality_settings()
    commands.extend(distribution.benchmark_command(tmp_path, settings))

    assert str(tmp_path / "test-results" / "quick.xml") in commands
    assert f"xml:{tmp_path / 'coverage' / 'coverage.xml'}" in commands
    assert "--cov-fail-under=74" in commands
    assert "--benchmark-disable-gc" in commands
    assert "--benchmark-min-rounds=5" in commands
    assert str(tmp_path / "benchmarks" / "core.json") in commands
    assert commands[-1] == "tests"
    assert "tests/unit/domain" not in commands
    assert str(tmp_path / "test-results" / "integration.xml") in commands
    assert str(tmp_path / "test-results" / "deep.xml") in commands


def test_benchmark_contract_rejects_performance_regression(tmp_path: Path) -> None:
    """平均時間が設定上限を超えたbenchmarkを品質違反にする。"""

    result = tmp_path / "benchmark.json"
    result.write_text(
        json.dumps(
            {
                "benchmarks": [
                    {
                        "name": "core",
                        "stats": {"mean": 0.011},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    errors, measurements = distribution.benchmark_contract(result, maximum_mean_ms=10)

    assert measurements == [("core", 11.0)]
    assert errors == ["coreの平均11.000msが上限10msを超えました。"]


def test_benchmark_contract_accepts_result_within_limit(tmp_path: Path) -> None:
    """設定上限内のbenchmark結果を受理する。"""

    result = tmp_path / "benchmark.json"
    result.write_text(
        json.dumps(
            {
                "benchmarks": [
                    {
                        "name": "core",
                        "stats": {"mean": 0.001},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert distribution.benchmark_contract(result, maximum_mean_ms=10) == (
        [],
        [("core", 1.0)],
    )


def test_distribution_contract_reports_missing_resources_and_entrypoints(
    tmp_path: Path,
) -> None:
    """配布物の欠落をCheckで調査可能な粒度へ分解する。"""

    _write_contract_sdist(tmp_path / "package.tar.gz")
    with ZipFile(tmp_path / "package.whl", "w") as wheel:
        wheel.writestr("package.dist-info/entry_points.txt", "[console_scripts]\n")

    errors = distribution.distribution_contract_errors(tmp_path)

    assert any("defaults.toml" in error for error in errors)
    assert any("werewolf-agent =" in error for error in errors)
    assert any("werewolf-agent-worker =" in error for error in errors)


def test_distribution_contract_accepts_complete_wheel(tmp_path: Path) -> None:
    """全resourceとconsole entrypointを含む配布物を受理する。"""

    _write_contract_sdist(tmp_path / "package.tar.gz")
    resources, entrypoints = distribution.distribution_contract()
    with ZipFile(tmp_path / "package.whl", "w") as wheel:
        wheel.writestr(
            "package.dist-info/entry_points.txt",
            "[console_scripts]\n" + "\n".join(entrypoints) + "\n",
        )
        for resource in resources:
            wheel.writestr(resource, "content")

    assert distribution.distribution_contract_errors(tmp_path) == []


def test_distribution_contract_rejects_unreadable_sdist(tmp_path: Path) -> None:
    """壊れたsource配布物を存在だけで合格させない。"""

    (tmp_path / "package.tar.gz").write_bytes(b"not-a-tar")
    resources, entrypoints = distribution.distribution_contract()
    with ZipFile(tmp_path / "package.whl", "w") as wheel:
        wheel.writestr(
            "package.dist-info/entry_points.txt",
            "[console_scripts]\n" + "\n".join(entrypoints) + "\n",
        )
        for resource in resources:
            wheel.writestr(resource, "content")

    errors = distribution.distribution_contract_errors(tmp_path)

    assert any("sdistを読み取れません" in error for error in errors)
