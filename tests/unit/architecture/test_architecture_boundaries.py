import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "backend" / "src" / "werewolf_agent"


def test_interface_entrypoints_do_not_import_domain_or_usecase_directly() -> None:
    forbidden_prefixes = (
        "werewolf_agent.domain",
        "werewolf_agent.usecase",
        "werewolf_agent.llm",
    )

    imported = _imports_under(PACKAGE / "interface" / "api")
    imported.extend(_imports_under(PACKAGE / "interface" / "cui"))
    imported.extend(_imports_under(PACKAGE / "interface" / "streamlit"))

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
        and module != "werewolf_agent.interface.application.errors"
    ]


def test_interface_imports_only_public_usecase_jobs_from_application_bridge() -> None:
    imported = _imports_under(PACKAGE / "interface")
    application_path = PACKAGE / "interface" / "application"
    allowed_prefix = "werewolf_agent.usecase.jobs"

    assert not [
        (path, module)
        for path, module in imported
        if (module == "werewolf_agent.usecase" or module.startswith("werewolf_agent.usecase."))
        and (
            not path.is_relative_to(application_path)
            or not (module == allowed_prefix or module.startswith(f"{allowed_prefix}."))
        )
    ]


def test_usecase_only_imports_public_domain_entrypoints() -> None:
    allowed_domain_modules = {
        "werewolf_agent.domain.models",
        "werewolf_agent.domain.service",
    }

    imported = _imports_under(PACKAGE / "usecase")
    bad_imports = []
    for path, module in imported:
        if not module.startswith("werewolf_agent.domain"):
            continue
        if module not in allowed_domain_modules:
            bad_imports.append((path, module))

    assert not bad_imports


def test_domain_does_not_import_outer_layers() -> None:
    forbidden_prefixes = (
        "werewolf_agent.usecase",
        "werewolf_agent.interface",
        "werewolf_agent.commons",
        "werewolf_agent.llm",
    )

    imported = _imports_under(PACKAGE / "domain")

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    ]


def _imports_under(path: Path) -> list[tuple[Path, str]]:
    imported: list[tuple[Path, str]] = []
    for source_path in path.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend((source_path, alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.append((source_path, node.module))
    return imported
