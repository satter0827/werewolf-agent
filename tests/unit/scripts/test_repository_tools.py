"""repository直下の開発tool構成を検査する。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"


def test_scripts_directory_keeps_only_python_modules() -> None:
    """scriptsの実行形式をPythonへ統一する。"""
    paths = [path for path in SCRIPTS.iterdir() if path.is_file()]

    assert paths
    assert all(path.name in {"AGENTS.md", "README.md"} or path.suffix == ".py" for path in paths)


def test_public_tool_packages_expose_module_entrypoints() -> None:
    """公開tool packageが共通のmodule実行形式を持つ。"""
    for name in (
        "architecture",
        "browser",
        "contracts",
        "docs",
        "environment",
        "quality",
        "supabase",
    ):
        package = SCRIPTS / name
        assert (package / "__init__.py").is_file()
        assert (package / "__main__.py").is_file()


def test_generated_artifacts_stay_out_of_repository_root() -> None:
    """代表的なローカル成果物をrepository直下へ生成しない。"""
    for name in (
        ".benchmarks",
        ".coverage",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "coverage.xml",
        "dist",
        "htmlcov",
    ):
        assert not (ROOT / name).exists()


def test_sdist_exposes_only_python_build_inputs() -> None:
    """開発用surfaceをsdistへ含めない。"""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    sdist = pyproject.split("[tool.hatch.build.targets.sdist]", maxsplit=1)[1].split(
        "[tool.pytest.ini_options]",
        maxsplit=1,
    )[0]

    assert '"src",' in sdist
    for private_surface in ('"docker",', '"docs",', '"scripts",', '"tests",'):
        assert private_surface not in sdist
