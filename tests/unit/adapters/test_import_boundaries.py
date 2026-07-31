"""Adapter packageのoptional依存境界を検査する。"""

from __future__ import annotations

import subprocess
import sys


def test_adapter_packages_do_not_eagerly_load_optional_integrations() -> None:
    """集約packageのimportでHTTP、Auth、database実装を読み込まない。"""
    checked = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import werewolf_agent.adapters; "
                "import werewolf_agent.adapters.supabase; "
                "forbidden = ("
                "'werewolf_agent.adapters.factory', "
                "'werewolf_agent.adapters.supabase.auth_client', "
                "'werewolf_agent.adapters.supabase.pool', "
                "'werewolf_agent.adapters.supabase.session_store'"
                "); "
                "assert not set(forbidden).intersection(sys.modules)"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert checked.returncode == 0, checked.stdout + checked.stderr
