"""Tracked fileと新規fileからcredential候補を検出する。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from detect_secrets.core import baseline
from detect_secrets.core.secrets_collection import SecretsCollection
from detect_secrets.settings import transient_settings

from scripts._infra.process import REPOSITORY_ROOT

BASELINE_PATH = REPOSITORY_ROOT / ".secrets.baseline"


def audit_secrets() -> int:
    """監査済みbaselineにないsecret候補を拒否する。"""
    if not _utf8_mode_enabled():
        completed = subprocess.run(
            (sys.executable, "-X", "utf8", "-m", "scripts.security", "secrets"),
            cwd=REPOSITORY_ROOT,
            check=False,
        )
        return completed.returncode
    listed = subprocess.run(
        ("git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"),
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
    )
    if listed.returncode != 0:
        return listed.returncode
    paths = tuple(
        decoded
        for path in listed.stdout.split(b"\0")
        if path and (decoded := os.fsdecode(path)) != BASELINE_PATH.name
    )
    return _scan_paths(paths, BASELINE_PATH)


def _utf8_mode_enabled() -> bool:
    """File読込がOS localeに依存しない実行modeかを返す。"""
    return bool(sys.flags.utf8_mode)


def _scan_paths(paths: tuple[str, ...], baseline_path: Path) -> int:
    """Baselineを書き換えず、同一設定で全fileを比較する。"""
    try:
        baseline_data = baseline.load_from_file(str(baseline_path))
        with transient_settings(baseline_data):
            approved = SecretsCollection.load_from_baseline(baseline_data)
            detected = SecretsCollection()
            for path in paths:
                detected.scan_file(path)
            new_secrets = detected - approved
    except Exception as error:
        print(f"secret scan failed: {error}", file=sys.stderr)
        return 1
    if not new_secrets:
        return 0
    print("Potential secrets were detected:", file=sys.stderr)
    for _filename, secret in new_secrets:
        print(secret, file=sys.stderr)
    return 1


__all__ = ["BASELINE_PATH", "audit_secrets"]
