"""Repositoryで使用するNode.js toolchainを解決する。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

REQUIRED_NODE_MAJOR = 22
NODE_HOME_ENVIRONMENT = "WEREWOLF_NODE_HOME"


def node_executable() -> str:
    """Node.js 22を優先し、見つからない場合は通常の実行fileを返す。"""
    fallback = shutil.which("node")
    for candidate in _candidate_nodes(fallback):
        if candidate.is_file() and _major_version(candidate) == REQUIRED_NODE_MAJOR:
            return str(candidate)
    return fallback or "node"


def npm_executable() -> str:
    """選択したNode.jsと同じdirectoryのnpmを返す。"""
    node = Path(node_executable())
    sibling = node.with_name("npm.cmd" if sys.platform == "win32" else "npm")
    if sibling.is_file():
        return str(sibling)
    return shutil.which("npm") or "npm"


def preferred_node_directory() -> Path | None:
    """対応するNode.jsのbinary directoryがあれば返す。"""
    node = Path(node_executable())
    if node.is_file() and _major_version(node) == REQUIRED_NODE_MAJOR:
        return node.parent
    return None


def _candidate_nodes(fallback: str | None) -> Iterable[Path]:
    configured_home = os.environ.get(NODE_HOME_ENVIRONMENT, "").strip()
    if configured_home:
        yield Path(configured_home) / _node_name()
    if fallback:
        yield Path(fallback)
    if sys.platform == "win32":
        yield Path.home() / "scoop" / "apps" / "nodejs22" / "current" / "node.exe"


def _node_name() -> str:
    return "node.exe" if sys.platform == "win32" else "node"


def _major_version(executable: Path) -> int | None:
    try:
        completed = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=10,
        )
        return int(completed.stdout.strip().lstrip("v").split(".", 1)[0])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


__all__ = [
    "NODE_HOME_ENVIRONMENT",
    "REQUIRED_NODE_MAJOR",
    "node_executable",
    "npm_executable",
    "preferred_node_directory",
]
