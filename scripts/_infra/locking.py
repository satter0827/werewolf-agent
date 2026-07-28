"""外部依存を必要としないprocess間file lock。"""

from __future__ import annotations

import errno
import importlib
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

LOCK_RETRY_SECONDS = 0.05


class LockTimeoutError(TimeoutError):
    """指定時間内にfile lockを取得できない。"""


@contextmanager
def exclusive_file_lock(path: Path, *, timeout_seconds: float) -> Iterator[None]:
    """同一fileを使うprocess間で排他区間を形成する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    with path.open("a+b") as stream:
        _ensure_lock_byte(stream)
        while True:
            try:
                _lock(stream)
                break
            except OSError as error:
                if not _is_lock_contention(error) or time.monotonic() >= deadline:
                    if _is_lock_contention(error):
                        raise LockTimeoutError(path) from error
                    raise
                time.sleep(LOCK_RETRY_SECONDS)
        try:
            yield
        finally:
            _unlock(stream)


def _ensure_lock_byte(stream: BinaryIO) -> None:
    stream.seek(0, os.SEEK_END)
    if stream.tell() == 0:
        stream.write(b"\0")
        stream.flush()


def _lock(stream: BinaryIO) -> None:
    stream.seek(0)
    if os.name == "nt":
        msvcrt = importlib.import_module("msvcrt")
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        return
    fcntl = importlib.import_module("fcntl")
    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(stream: BinaryIO) -> None:
    stream.seek(0)
    if os.name == "nt":
        msvcrt = importlib.import_module("msvcrt")
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        return
    fcntl = importlib.import_module("fcntl")
    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _is_lock_contention(error: OSError) -> bool:
    return error.errno in {errno.EACCES, errno.EAGAIN} or getattr(error, "winerror", None) in {
        33,
        36,
    }


__all__ = ["LockTimeoutError", "exclusive_file_lock"]
