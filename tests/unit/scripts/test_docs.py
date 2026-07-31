"""Sphinx 文書の公開構造テスト。"""

from __future__ import annotations

import ast
import runpy
import tomllib
from pathlib import Path
from types import ModuleType

import pytest
from scripts.docs import building
from scripts.docs import inspection as docs
from scripts.quality import runner as quality

from werewolf_agent import application

ROOT = Path(__file__).resolve().parents[3]


def test_documentation_structure_and_style_pass() -> None:
    """lifecycle、到達性、公開API、表記規則を安定した契約として検査する。"""
    report = docs.inspect_documentation()

    assert report["status"] == "passed"
    assert report["findings"] == []
    assert set(report["labels"]) >= docs.REQUIRED_LABELS
    assert set(report["automodules"]) == docs.PUBLIC_API_MODULES


def test_sphinx_configuration_uses_japanese_furo_contract() -> None:
    """生成HTMLのtheme、言語、検索、標準extensionを固定する。"""
    configuration = (ROOT / "docs" / "conf.py").read_text(encoding="utf-8")

    assert 'html_theme = "furo"' in configuration
    assert 'language = "ja"' in configuration
    assert 'html_search_language = "ja"' in configuration
    assert 'myst_enable_extensions = ["colon_fence"]' in configuration
    assert '"sphinx_copybutton"' in configuration
    assert '"sphinx_design"' in configuration
    assert '"On this page": "このページ内"' in configuration
    assert "alabaster" not in configuration
    assert 'autodoc_default_options = {"exclude-members": "model_config"}' in configuration


def test_automodule_directives_require_eval_rst_and_remain_unique() -> None:
    """autodocのRST出力をMyST本文として誤解釈させない。"""
    correct = """```{eval-rst}\n.. automodule:: werewolf_agent.domain\n   :members:\n```"""
    old = """```{automodule} werewolf_agent.domain\n:members:\n```"""

    assert docs._eval_rst_automodules(correct) == ("werewolf_agent.domain",)
    assert docs._DIRECT_AUTOMODULE_PATTERN.search(old)
    assert docs._eval_rst_automodules(old) == ()


def test_python_api_html_requires_modules_objects_and_no_raw_directives(
    tmp_path: Path,
) -> None:
    """生成HTMLの意味構造と可視textを検査する。"""
    path = tmp_path / "python-api.html"
    path.write_text(
        """
<section id="module-werewolf_agent"></section>
<section id="module-werewolf_agent.agents"></section>
<section id="module-werewolf_agent.domain"></section>
<section id="module-werewolf_agent.application"></section>
<section id="module-werewolf_agent.simulation"></section>
<section id="module-werewolf_agent.setup"></section>
<dl class="py class"><dt id="werewolf_agent.domain.Game">Game</dt></dl>
""",
        encoding="utf-8",
    )
    assert building._python_api_html_findings(path) == []

    path.write_text("<p>.. py:class:: Game :canonical:</p>", encoding="utf-8")
    rule_ids = {item["rule_id"] for item in building._python_api_html_findings(path)}
    assert rule_ids == {
        "DOC-API-HTML-002",
        "DOC-API-HTML-003",
        "DOC-API-HTML-004",
    }


def test_python_api_html_uses_manifest_modules_and_rejects_any_raw_py_directive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """公開moduleの正本と一般化したPython directive検査を共有する。"""
    synthetic = ModuleType("werewolf_agent.synthetic")
    monkeypatch.setattr(building, "PUBLIC_MODULES", (synthetic,))
    path = tmp_path / "python-api.html"
    path.write_text(
        """
<section id="module-werewolf_agent.synthetic"></section>
<dl class="py function"><dt>function</dt></dl>
<p>.. py:function:: leaked</p>
""",
        encoding="utf-8",
    )

    findings = building._python_api_html_findings(path)

    assert [item["rule_id"] for item in findings] == ["DOC-API-HTML-004"]


def test_pydantic_signature_preserves_default_factory_parameters() -> None:
    """Autodoc署名でdefault factory付きfieldを必須扱いしない。"""
    configuration = runpy.run_path(ROOT / "docs" / "conf.py")

    signature, _ = configuration["_pydantic_signature"](
        None,
        "class",
        "werewolf_agent.application.GameRevealResult",
        application.GameRevealResult,
        None,
        None,
        None,
    )

    assert signature.count("<factory>") == 4


def test_python_api_snippets_execute_without_external_services() -> None:
    """掲載例を外部serviceなしで実行できる状態に保つ。"""
    for name in (
        "python_api_agents.py",
        "python_api_application.py",
        "python_api_domain.py",
        "python_api_setup.py",
        "python_api_simulation.py",
    ):
        runpy.run_path(ROOT / "docs" / "snippets" / name, run_name="__main__")


def test_documentation_style_removes_code_and_link_targets() -> None:
    """表記検査は説明文だけを対象とし、識別子とlink targetを変更しない。"""
    text = """
repositoryを説明します。
`repository command`
[source](docs/source.md)
```powershell
python -m scripts.quality profile
```
"""

    prose = docs._style_prose(text)

    assert "repositoryを説明します。" in prose
    assert "repository command" not in prose
    assert "docs/source.md" not in prose
    assert "scripts.quality profile" not in prose


def test_documentation_style_detects_polite_and_split_japanese_prose() -> None:
    """常体と日本語の語間空白を機械検査できるようにする。"""
    assert docs._POLITE_SENTENCE_PATTERN.search("設計書を参照してください。")
    assert docs._JAPANESE_WORD_SPACING_PATTERN.search("公開 モジュール を説明する。")
    assert not docs._JAPANESE_WORD_SPACING_PATTERN.search("Local LLMを使う。")


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
    assert frozenset({"AGENTS.md", "README.md", "scripts/README.md"}) == (
        docs.QUALITY_COMMAND_OWNERS
    )
    assert "react" in docs.OBSOLETE_REFERENCES
    assert docs._obsolete_reference_offset("react client", "react") == 0
    assert docs._obsolete_reference_offset("death_reaction", "react") == -1
    assert docs._obsolete_reference_offset("npmを使う", "npm") == 0
    allowed = docs.OBSOLETE_REFERENCE_ALLOWLIST["docs/notes/retired-browser-ui-reintroduction.md"]
    assert "react" in allowed
    assert ".werewolf-agent/quality/latest" not in allowed
    assert docs._VERIFICATION_COMMAND_PATTERN.search("python -m scripts.quality check")
    assert docs._VERIFICATION_COMMAND_PATTERN.search("werewolf-agent system doctor")


def test_public_repository_documents_are_canonical_sources() -> None:
    """利用、参加、脆弱性報告の入口を文書検査の対象に含める。"""
    paths = {path.name for path in docs.CANONICAL_DOCUMENT_PATHS}

    assert {"README.md", "CONTRIBUTING.md", "SECURITY.md"} <= paths


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
