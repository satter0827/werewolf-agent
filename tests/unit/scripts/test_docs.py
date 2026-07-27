"""Sphinx 文書の公開構造テスト。"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest
from scripts.docs import inspection as docs
from scripts.quality import runner as quality

ROOT = Path(__file__).resolve().parents[3]


def test_documentation_structure_passes_without_constraining_prose() -> None:
    """lifecycle、到達性、公開APIだけを安定した構造として検査する。"""
    report = docs.inspect_documentation()

    assert report["status"] == "passed"
    assert report["findings"] == []
    assert set(report["labels"]) >= docs.REQUIRED_LABELS
    assert set(report["automodules"]) == docs.PUBLIC_API_MODULES


def test_documentation_runner_is_independent_from_quality_orchestration() -> None:
    """文書runnerから全体品質runnerへの依存を禁止する。"""
    path = ROOT / "scripts" / "docs" / "building.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    )

    assert "scripts.quality" not in imported


def test_sphinx_configuration_keeps_generated_analysis_out_of_source() -> None:
    """生成済み分析をsource管理せずbuild時だけ文書へ組み込む。"""
    configuration = (ROOT / "docs" / "conf.py").read_text(encoding="utf-8")
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert '"_generated/**"' in configuration
    assert ".werewolf-agent" in ignore


def test_published_api_docstrings_use_an_unsuppressed_google_gate() -> None:
    """公開APIのdocstring規約と品質gateを設定変更から保護する。"""
    with (ROOT / "pyproject.toml").open("rb") as stream:
        pyproject = tomllib.load(stream)
    gates = [
        gate
        for stage in quality._profile_stages("focus", jobs=1)
        for gate in stage
        if gate.name == "docstrings"
    ]

    assert pyproject["tool"]["ruff"]["lint"]["pydocstyle"]["convention"] == "google"
    assert len(gates) == 1
    command = gates[0].command
    assert command[1:5] == ("-m", "ruff", "check", "--select")
    assert "--no-cache" not in command
    assert "D" in command
    assert "src/werewolf_agent" in command
    assert "--ignore" not in command


def test_toctree_targets_support_nested_relative_and_external_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """入れ子の文書構成を許容し、外部URLをlocal文書として扱わない。"""
    root = tmp_path / "docs"
    path = root / "design" / "index.md"
    path.parent.mkdir(parents=True)
    monkeypatch.setattr(docs, "DOCS_ROOT", root)
    text = """
```{toctree}

guide/getting-started
API reference <../reference/python-api.md>
Project <https://example.com/project>
```
"""

    assert docs._toctree_targets(path, text) == {
        "design/guide/getting-started",
        "reference/python-api",
    }


def test_documentation_reference_detection_covers_links_and_repository_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """local linkとsource pathを別々の基準位置から検査する。"""
    root = tmp_path / "repository"
    source = root / "src" / "werewolf_agent" / "domain" / "game.py"
    contract = root / "contracts" / "openapi.json"
    source.parent.mkdir(parents=True)
    source.touch()
    contract.parent.mkdir(parents=True)
    contract.touch()
    monkeypatch.setattr(docs, "REPOSITORY_ROOT", root)
    text = "[Guide](guide.md) `domain/game.py` `src/missing.py`"

    assert docs._local_markdown_links(text) == [("guide.md", 8)]
    assert [reference for reference, _ in docs._repository_path_references(text)] == [
        "domain/game.py",
        "src/missing.py",
    ]
    assert docs._repository_reference_target("domain/game.py") == source.resolve()
    assert docs._repository_reference_target("contracts/openapi.json") == contract.resolve()
    assert not docs._repository_reference_target("src/missing.py").exists()


def test_documentation_policy_identifies_obsolete_references_and_command_owners() -> None:
    """旧構造と品質commandの正本を明示したpolicyとして固定する。"""
    assert "interfaces/worker" in docs.OBSOLETE_REFERENCES
    assert ".werewolf-agent/quality/latest" in docs.OBSOLETE_REFERENCES
    assert frozenset({"README.md", "scripts/README.md"}) == docs.QUALITY_COMMAND_OWNERS
    assert docs._QUALITY_COMMAND_PATTERN.search("python -m scripts.quality check")


def test_docstring_suppression_detection_covers_source_and_configuration() -> None:
    """bare noqa、file-level noqa、Ruff設定によるD系回避を検出する。"""
    pattern = docs._DOCSTRING_SUPPRESSION_PATTERN

    assert pattern.search("def f():  # noqa")
    assert pattern.search("# ruff: noqa: D")
    assert pattern.search("# flake8: noqa: D417")
    assert not pattern.search("from package import value  # noqa: F401")

    configuration = {
        "tool": {
            "ruff": {
                "lint": {
                    "ignore": ["E501"],
                    "per-file-ignores": {
                        "tests/**/*.py": ["D"],
                        "src/**/*.py": ["D417"],
                    },
                }
            }
        }
    }
    assert docs._docstring_configuration_suppressions(configuration) == [
        "pyproject.toml:tool.ruff.lint.per-file-ignores.src/**/*.py"
    ]
