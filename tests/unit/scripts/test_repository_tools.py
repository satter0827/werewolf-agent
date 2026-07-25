"""repository直下の開発tool構成を検査する。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"


def test_scripts_directory_keeps_only_python_modules() -> None:
    """scriptsの実行形式をPythonへ統一する。"""
    paths = [path for path in SCRIPTS.iterdir() if path.is_file()]

    assert paths
    assert all(path.name == "README.md" or path.suffix == ".py" for path in paths)


def test_expected_python_tools_exist() -> None:
    """開発と品質管理に必要なmoduleを明示する。"""
    for name in (
        "__init__.py",
        "_support.py",
        "architecture.py",
        "apply_migrations.py",
        "docs.py",
        "e2e.py",
        "export_openapi.py",
        "preflight_supabase.py",
        "quality.py",
    ):
        assert (SCRIPTS / name).is_file()


def test_sdist_exposes_only_python_build_inputs() -> None:
    """開発用surfaceをsdistへ含めない。"""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    sdist = pyproject.split("[tool.hatch.build.targets.sdist]", maxsplit=1)[1].split(
        "[tool.pytest.ini_options]",
        maxsplit=1,
    )[0]

    assert '"src",' in sdist
    for private_surface in ('"docker",', '"docs",', '"frontend",', '"scripts",', '"tests",'):
        assert private_surface not in sdist
