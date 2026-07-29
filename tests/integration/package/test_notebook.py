"""構築済みwheelとリポジトリ向けNotebookの隔離実行を検査する。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_OUTPUT = ROOT / ".werewolf-agent" / "outputs" / "package"


def _wheel() -> Path:
    wheels = list(PACKAGE_OUTPUT.glob("*.whl"))
    assert len(wheels) == 1, "先にcheck profileで配布物を構築してください。"
    return wheels[0]


@pytest.mark.serial
def test_wheel_installs_and_exposes_the_root_domain_api(tmp_path: Path) -> None:
    """source checkout外のvenvでwheelのroot APIをimportする。"""
    environment = tmp_path / "environment"
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(environment)
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    installed = subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(_wheel())],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr

    checked = subprocess.run(
        [
            str(python),
            "-c",
            (
                "from pathlib import Path; "
                "import sys; "
                "from werewolf_agent import Action, Game, GameSetup, Player, build_game_rules; "
                "import werewolf_agent; "
                "assert Path(werewolf_agent.__file__).resolve().is_relative_to("
                "Path(sys.argv[1]).resolve()); "
                "assert all((Action, Game, GameSetup, Player, build_game_rules)); "
                "print(werewolf_agent.__version__)"
            ),
            str(environment),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert checked.stdout.strip() == "0.2.0"


@pytest.mark.serial
def test_notebook_executes_against_wheel_without_source_or_scripts(tmp_path: Path) -> None:
    """Notebook一式だけをコピーし、展開wheelを使って全セルを実行する。"""
    wheel_root = tmp_path / "wheel"
    with ZipFile(_wheel()) as wheel:
        wheel.extractall(wheel_root)
    notebook_root = tmp_path / "notebooks"
    shutil.copytree(ROOT / "notebooks", notebook_root)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join((str(wheel_root), str(notebook_root)))
    script = """
from pathlib import Path
import sys

import nbformat
from nbclient import NotebookClient
import werewolf_agent

wheel_root = Path(sys.argv[1]).resolve()
assert Path(werewolf_agent.__file__).resolve().is_relative_to(wheel_root)
notebook = nbformat.read("quickstart.ipynb", as_version=4)
NotebookClient(
    notebook,
    timeout=120,
    kernel_name="python3",
    resources={"metadata": {"path": str(Path.cwd())}},
).execute()
code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
assert all(cell.execution_count is not None for cell in code_cells)
assert not [
    output
    for cell in code_cells
    for output in cell.outputs
    if output.output_type == "error"
]
assert max(
    sum(len(str(output)) for output in cell.outputs)
    for cell in code_cells
) < 2000
"""
    executed = subprocess.run(
        [sys.executable, "-c", script, str(wheel_root)],
        cwd=notebook_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert executed.returncode == 0, executed.stdout + executed.stderr
    assert not (notebook_root / "scripts").exists()
    assert not (notebook_root / "src").exists()
