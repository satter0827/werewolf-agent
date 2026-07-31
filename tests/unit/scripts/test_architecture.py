"""Architecture analysis command の構造テスト。"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from scripts.architecture import analysis as architecture
from scripts.architecture import rendering


def test_architecture_analysis_passes_and_exposes_evidence() -> None:
    """依存評価に層、module、import元行、公開APIを含める。"""
    document = architecture.analyze()

    assert document["status"] == "passed"
    assert document["findings"] == []
    assert document["layers"]
    assert document["modules"]
    assert document["import_evidence"]
    assert document["dependency_exceptions"] == [
        {
            "source_module": "werewolf_agent.api.bootstrap",
            "target_layer": "adapters",
            "reason": "HTTP composition rootがadapter実装を構築する。",
        }
    ]
    assert set(document["public_symbols"]) == {
        "werewolf_agent",
        "werewolf_agent.application",
        "werewolf_agent.domain",
        "werewolf_agent.setup",
    }
    assert all(edge["line"] > 0 for edge in document["import_evidence"])


def test_architecture_outputs_are_complete_and_deterministic(tmp_path: Path) -> None:
    """同じsourceから機械可読データ、評価、図を安定して生成する。"""
    first = tmp_path / "first"
    second = tmp_path / "second"

    architecture.write_outputs(first)
    architecture.write_outputs(second)

    expected = {
        "architecture.json",
        "architecture.schema.json",
        "assessment.md",
        "domain-structure.svg",
        "layer-dependencies.svg",
        "system-context.svg",
    }
    assert {path.name for path in first.iterdir()} == expected
    for name in expected:
        assert (first / name).read_bytes() == (second / name).read_bytes()

    schema = json.loads((first / "architecture.schema.json").read_text(encoding="utf-8"))
    document = json.loads((first / "architecture.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(document)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == architecture.SCHEMA_VERSION
    assert "dependency_exceptions" in schema["required"]


def test_diagram_edges_end_at_node_boundaries() -> None:
    """矢印の向きがnode背面に隠れないよう接続点を外周へ置く。"""
    horizontal = rendering._edge_endpoints(
        (0, 0),
        (300, 0),
        box_width=180,
        box_height=64,
    )
    diagonal = rendering._edge_endpoints(
        (0, 0),
        (300, 150),
        box_width=180,
        box_height=64,
    )

    assert horizontal == (180.0, 32.0, 300.0, 32.0)
    assert diagonal == (154.0, 64.0, 326.0, 150.0)


def test_import_analysis_resolves_relative_and_package_imports(tmp_path: Path) -> None:
    """構造分析がrelative importとpackage直下のsubmodule importを見落とさない。"""
    path = tmp_path / "sample.py"
    path.write_text(
        "\n".join(
            [
                "from typing import TYPE_CHECKING",
                "from ..contracts import ProblemDetails",
                "from werewolf_agent import domain",
                "if TYPE_CHECKING:",
                "    from ..clients import cli",
            ]
        ),
        encoding="utf-8",
    )

    imports = architecture.imports_with_lines(
        path,
        "werewolf_agent.api.sample",
    )

    assert ("werewolf_agent.contracts", 2) in imports
    assert ("werewolf_agent.domain", 3) in imports
    assert not any(name.startswith("werewolf_agent.clients") for name, _ in imports)


def test_project_module_resolution_prefers_the_deepest_real_module() -> None:
    modules = {
        "werewolf_agent": Path("root.py"),
        "werewolf_agent.application": Path("application.py"),
        "werewolf_agent.application.models": Path("models.py"),
    }

    assert (
        architecture._project_module_name(
            "werewolf_agent.application.models.GameResult",
            modules,
        )
        == "werewolf_agent.application.models"
    )
    assert (
        architecture._project_module_name(
            "werewolf_agent.application.GameApplication",
            modules,
        )
        == "werewolf_agent.application"
    )
    assert architecture._project_module_name("httpx.Client", modules) is None


def test_analysis_rejects_imports_from_an_explicit_public_alias(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """明示構成した公開aliasで内部依存規則を迂回させない。"""
    package = tmp_path / "src" / "werewolf_agent"
    application = package / "application"
    domain = package / "domain"
    application.mkdir(parents=True)
    domain.mkdir()
    (package / "__init__.py").write_text(
        "from werewolf_agent.domain import Game\n",
        encoding="utf-8",
    )
    (application / "__init__.py").write_text("", encoding="utf-8")
    (application / "service.py").write_text(
        "from werewolf_agent import Game\n",
        encoding="utf-8",
    )
    (application / "types.py").write_text(
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from werewolf_agent import Game\n",
        encoding="utf-8",
    )
    (domain / "__init__.py").write_text("class Game: pass\n", encoding="utf-8")
    monkeypatch.setattr(architecture, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(architecture, "PACKAGE_ROOT", package)
    monkeypatch.setattr(
        architecture,
        "PUBLIC_ALIAS_MODULE_NAMES",
        frozenset({"werewolf_agent"}),
    )
    modules = {architecture.module_name(path): path for path in sorted(package.rglob("*.py"))}

    findings = architecture._internal_public_alias_findings(modules)

    assert [finding.rule_id for finding in findings] == [
        "ARCH-DEPENDENCY-002",
        "ARCH-DEPENDENCY-002",
    ]
    assert {finding.evidence["source_module"] for finding in findings} == {
        "werewolf_agent.application.service",
        "werewolf_agent.application.types",
    }
