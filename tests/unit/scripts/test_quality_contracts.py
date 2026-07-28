"""生成contract品質gateの比較契約を検査する。"""

from pathlib import Path

import pytest
from scripts._infra.process import CommandResult
from scripts.contracts import openapi
from scripts.quality import runner as quality
from scripts.quality.gates import contracts


def test_contract_comparison_ignores_platform_newline_difference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同じ生成内容をWindows改行だけで品質違反にしない。"""
    (tmp_path / "contracts").mkdir()
    (tmp_path / "contracts" / "openapi.json").write_text(
        "{\n}\n",
        encoding="utf-8",
        newline="\r\n",
    )
    run_dir = tmp_path / "run"
    context = quality.RunContext(
        profile="gate-contracts",
        jobs=1,
        timeout_seconds=60,
        run_id="run",
        run_dir=run_dir,
        environment={},
        started_at=quality.utc_now(),
    )

    def run(
        command: list[str],
        *,
        cwd: Path = tmp_path,
        **_kwargs: object,
    ) -> CommandResult:
        if "--output" in command:
            Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(command[-1]).write_text("{\n}\n", encoding="utf-8", newline="\n")
        return CommandResult(command, 0, 0.0, "")

    monkeypatch.setattr(contracts, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(contracts, "run_command", run)

    result = contracts.check_openapi_contract(context, tmp_path / "log")

    assert result.returncode == 0


def test_contract_cli_defaults_to_tracked_repository_contract() -> None:
    """公開moduleの既定出力をscripts配下ではなくGit管理契約へ向ける。"""
    output = openapi.build_parser().parse_args([]).output

    assert output == Path(__file__).resolve().parents[3] / "contracts" / "openapi.json"
