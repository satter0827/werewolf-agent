"""Process間file lockの契約。"""

from pathlib import Path

import pytest
from scripts._infra.locking import LockTimeoutError, exclusive_file_lock


def test_exclusive_file_lock_times_out_while_owned(tmp_path: Path) -> None:
    """同じlockを保持中の再取得をtimeoutとして拒否する。"""
    path = tmp_path / "operation.lock"

    with (
        exclusive_file_lock(path, timeout_seconds=0.1),
        pytest.raises(LockTimeoutError),
        exclusive_file_lock(path, timeout_seconds=0),
    ):
        pytest.fail("保持中のlockを再取得しました。")


def test_exclusive_file_lock_can_be_reacquired_after_release(tmp_path: Path) -> None:
    """排他区間の終了後は同じlockを再取得できる。"""
    path = tmp_path / "operation.lock"

    with exclusive_file_lock(path, timeout_seconds=0.1):
        pass
    with exclusive_file_lock(path, timeout_seconds=0.1):
        pass
