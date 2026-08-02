"""Lock済みの全依存を脆弱性databaseと照合する。"""

from __future__ import annotations

import subprocess
import sys

from scripts._infra.process import REPOSITORY_ROOT, TEMPORARY_ROOT


def audit_dependencies() -> int:
    """全extraとdependency groupをexportし、解決済みversionを監査する。"""
    audit_root = TEMPORARY_ROOT / "security"
    audit_root.mkdir(parents=True, exist_ok=True)
    requirements = audit_root / "requirements.txt"
    exported = subprocess.run(
        (
            "uv",
            "export",
            "--all-extras",
            "--all-groups",
            "--frozen",
            "--no-emit-project",
            "--output-file",
            str(requirements),
        ),
        cwd=REPOSITORY_ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
    )
    if exported.returncode != 0:
        return exported.returncode
    audited = subprocess.run(
        (
            sys.executable,
            "-m",
            "pip_audit",
            "--requirement",
            str(requirements),
            "--disable-pip",
            "--require-hashes",
            "--progress-spinner",
            "off",
        ),
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    return audited.returncode


__all__ = ["audit_dependencies"]
