"""構築済みwheelとリポジトリ向けNotebookの隔離実行を検査する。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
import venv
from pathlib import Path

import nbformat
import pytest

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_OUTPUT = ROOT / ".werewolf-agent" / "outputs" / "package"


def _wheel() -> Path:
    wheels = list(PACKAGE_OUTPUT.glob("*.whl"))
    assert len(wheels) == 1, "先にcheck profileで配布物を構築してください。"
    return wheels[0]


@pytest.fixture(scope="module")
def installed_wheel_environment(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path, dict[str, str]]:
    """wheelをinstallし、検証済み環境からNotebook実行依存だけを参照する。"""
    root = tmp_path_factory.mktemp("installed-wheel")
    environment = root / "environment"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    installed = subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(_wheel())],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr

    dependency_site_packages = Path(nbformat.__file__).resolve().parent.parent
    runtime_environment = os.environ.copy()
    runtime_environment.pop("PYTHONHOME", None)
    runtime_environment["PYTHONPATH"] = str(dependency_site_packages)
    return environment, python, runtime_environment


@pytest.mark.serial
def test_wheel_installs_and_exposes_the_owned_domain_api(
    installed_wheel_environment: tuple[Path, Path, dict[str, str]],
) -> None:
    """source checkout外のvenvでversionとdomain APIをimportする。"""
    environment, python, runtime_environment = installed_wheel_environment
    package_environment = runtime_environment.copy()
    package_environment.pop("PYTHONPATH", None)
    setup_path = environment.parent / "setup.json"
    setup_path.write_text(
        json.dumps(
            tomllib.loads(
                (
                    ROOT
                    / "src"
                    / "werewolf_agent"
                    / "application"
                    / "resources"
                    / "setups"
                    / "standard_6.toml"
                ).read_text(encoding="utf-8")
            )
        ),
        encoding="utf-8",
    )

    checked = subprocess.run(
        [
            str(python),
            "-c",
            (
                "from importlib.metadata import version; "
                "from pathlib import Path; "
                "import json; "
                "import sys; "
                "from werewolf_agent.domain import "
                "Action, Game, GameSetup, Player, build_game_rules; "
                "from werewolf_agent.agents import "
                "AgentContext, AgentFactory, AgentSession, DecisionRequest; "
                "from werewolf_agent.setup import "
                "GameSetupDocument, PlayerGenerationDefinition, PlayerIdentityDefinition, "
                "PrivateStrategyDefinition, PublicPersonaDefinition, generate_players; "
                "import werewolf_agent; "
                "generation = PlayerGenerationDefinition("
                "identities=(PlayerIdentityDefinition('Alice', 20, 30, 'female'),), "
                "public_personas=(PublicPersonaDefinition('calm', 'brief'),), "
                "private_strategies=(PrivateStrategyDefinition("
                "'analytic', 'low', 'claims'),)); "
                "assert generate_players(generation, player_count=1, seed=41) == "
                "generate_players(generation, player_count=1, seed=41); "
                "setup = GameSetupDocument.from_mapping("
                "json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))); "
                "first = generate_players(setup.player_generation, player_count=6, seed=41); "
                "second = generate_players(setup.player_generation, player_count=6, seed=41); "
                "assert first == second; "
                "rules = setup.to_rule_definition(); "
                "assert rules.player_count == 6; "
                "assert rules.role_counts == setup.mechanics.role_counts; "
                "assert Path(werewolf_agent.__file__).resolve().is_relative_to("
                "Path(sys.argv[1]).resolve()); "
                "assert all((Action, Game, GameSetup, Player, build_game_rules)); "
                "assert all((AgentContext, AgentFactory, AgentSession, DecisionRequest)); "
                "assert werewolf_agent.__all__ == ['__version__']; "
                "assert not hasattr(werewolf_agent, 'Game'); "
                "assert werewolf_agent.__version__ == version('werewolf-agent')"
            ),
            str(environment),
            str(setup_path),
        ],
        cwd=environment.parent,
        env=package_environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr


@pytest.mark.serial
@pytest.mark.parametrize(
    ("command", "extra"),
    (
        ("werewolf-agent", "cli"),
        ("werewolf-agent-api", "api"),
        ("werewolf-agent-worker", "worker"),
    ),
)
def test_standard_install_entrypoints_explain_the_required_extra(
    installed_wheel_environment: tuple[Path, Path, dict[str, str]],
    command: str,
    extra: str,
) -> None:
    """標準installのconsole scriptはtracebackなしで必要なextraを示す。"""
    environment, python, runtime_environment = installed_wheel_environment
    package_environment = runtime_environment.copy()
    package_environment.pop("PYTHONPATH", None)
    arguments = (
        [
            str(python),
            "-c",
            f"from werewolf_agent._entrypoints import {extra}; {extra}()",
        ]
        if sys.platform == "win32"
        else [str(environment / "bin" / command), "--help"]
    )

    executed = subprocess.run(
        arguments,
        cwd=environment.parent,
        env=package_environment,
        capture_output=True,
        text=True,
        check=False,
    )

    output = executed.stdout + executed.stderr
    assert executed.returncode != 0
    assert f"werewolf-agent[{extra}]" in output
    assert "Traceback" not in output


@pytest.mark.serial
def test_notebook_executes_against_wheel_without_source_or_scripts(
    tmp_path: Path,
    installed_wheel_environment: tuple[Path, Path, dict[str, str]],
) -> None:
    """wheel導入済みvenvでNotebook一式だけをコピーして全セルを実行する。"""
    environment, python, runtime_environment = installed_wheel_environment
    notebook_root = tmp_path / "notebooks"
    shutil.copytree(ROOT / "notebooks", notebook_root)
    kernel_name = "werewolf-demo-test"
    registered = subprocess.run(
        [
            str(python),
            "-m",
            "ipykernel",
            "install",
            "--prefix",
            str(environment),
            "--name",
            kernel_name,
        ],
        cwd=notebook_root,
        env=runtime_environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert registered.returncode == 0, registered.stdout + registered.stderr
    runtime_environment["JUPYTER_PATH"] = str(environment / "share" / "jupyter")
    script = """
from pathlib import Path
import sys

import nbformat
from nbclient import NotebookClient
import werewolf_agent

environment = Path(sys.argv[1]).resolve()
assert Path(sys.executable).resolve().is_relative_to(environment)
assert Path(werewolf_agent.__file__).resolve().is_relative_to(environment)
notebook = nbformat.read("quickstart.ipynb", as_version=4)
notebook.cells.insert(
    0,
    nbformat.v4.new_code_cell(
        "from pathlib import Path; import sys, werewolf_agent; "
        f"assert Path(sys.executable).resolve().is_relative_to(Path({str(environment)!r})); "
        f"assert Path(werewolf_agent.__file__).resolve().is_relative_to(Path({str(environment)!r}))"
    ),
)
NotebookClient(
    notebook,
    timeout=120,
    kernel_name=sys.argv[2],
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
        [str(python), "-c", script, str(environment), kernel_name],
        cwd=notebook_root,
        env=runtime_environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert executed.returncode == 0, executed.stdout + executed.stderr
    assert not (notebook_root / "scripts").exists()
    assert not (notebook_root / "src").exists()
