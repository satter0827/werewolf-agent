"""品質成果物を状態別に確定し、保持上限を適用する。"""

from __future__ import annotations

import json
import os
import shutil
import time
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from scripts._infra.artifacts import LAYOUT, REPOSITORY_ROOT

FAILURES_PER_SELECTOR = 3
FAILURE_BYTES_LIMIT = 100 * 1024 * 1024


def publish_run(run_dir: Path, selector: str, state: str) -> Path:
    """一時runを最新成功または保持対象failureとして確定する。"""
    failures_per_selector, failure_bytes_limit = _retention_settings()
    with _publication_lock():
        if state == "passed":
            kind = "gates" if selector.startswith("gate-") else "profiles"
            name = selector.removeprefix("gate-")
            target = LAYOUT.quality / "latest" / kind / name
            temporary = target.with_name(f".{target.name}.tmp")
            _replace_directory(temporary)
            temporary.mkdir(parents=True)
            for filename in ("report.json", "summary.md"):
                shutil.copy2(run_dir / filename, temporary / filename)
            _replace_directory(target)
            temporary.replace(target)
            shutil.rmtree(run_dir)
            return target / "report.json"

        target = LAYOUT.quality / "failures" / selector / run_dir.name
        target.parent.mkdir(parents=True, exist_ok=True)
        _replace_directory(target)
        omitted = _copy_failure(run_dir, target)
        _bound_failure(target, failure_bytes_limit, omitted)
        shutil.rmtree(run_dir)
        _prune_failures(target.parent, failures_per_selector)
        return target / "report.json"


def _copy_failure(source: Path, target: Path) -> list[tuple[str, int]]:
    """非成功gateの診断に必要な成果物だけを選択してコピーする。"""
    target.mkdir(parents=True)
    report_path = source / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    selected = {Path("report.json"), Path("summary.md")}
    for result in report.get("results", []):
        if not isinstance(result, dict) or result.get("state") in {"passed", "skipped"}:
            continue
        log = result.get("log")
        if isinstance(log, str):
            selected.add(Path(log))
        artifacts = result.get("artifacts")
        if isinstance(artifacts, list):
            for pattern in artifacts:
                if not isinstance(pattern, str):
                    continue
                selected.update(
                    path.relative_to(source)
                    for path in source.glob(pattern)
                    if path.is_file() and path.is_relative_to(source)
                )
    selected.update(
        path.relative_to(source)
        for path in (source / "test-results").glob("*.xml")
        if path.is_file()
    )
    copied: set[Path] = set()
    for relative in sorted(selected):
        path = source / relative
        if not path.is_file() or not path.is_relative_to(source):
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        copied.add(relative)
    return [
        (path.relative_to(source).as_posix(), path.stat().st_size)
        for path in source.rglob("*")
        if path.is_file() and path.relative_to(source) not in copied
    ]


def _bound_failure(
    root: Path,
    limit_bytes: int = FAILURE_BYTES_LIMIT,
    omitted: list[tuple[str, int]] | None = None,
) -> None:
    """診断価値の低い成果物から順に容量上限まで削減する。"""
    files = [path for path in root.rglob("*") if path.is_file()]
    total = sum(path.stat().st_size for path in files)
    omitted = list(omitted or [])
    removable = sorted(
        files, key=lambda path: (_retention_priority(path, root), path.stat().st_size), reverse=True
    )
    for path in removable:
        if total <= limit_bytes:
            break
        if path.name in {"report.json", "summary.md"}:
            continue
        size = path.stat().st_size
        omitted.append((path.relative_to(root).as_posix(), size))
        total -= size
        path.unlink()
    report_path = root / "report.json"
    document = json.loads(report_path.read_text(encoding="utf-8"))
    document["retention"] = {
        "omitted_artifacts": [path for path, _size in omitted],
        "omitted_count": len(omitted),
        "omitted_bytes": sum(size for _path, size in omitted),
        "limit_bytes": limit_bytes,
    }
    report_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _retention_priority(path: Path, root: Path) -> int:
    relative = path.relative_to(root)
    if relative.parts and relative.parts[0] == "logs":
        return 2
    if relative.parts and relative.parts[0] == "test-results":
        return 1
    return 3


def _prune_failures(root: Path, keep: int = FAILURES_PER_SELECTOR) -> None:
    runs = sorted(
        (path for path in root.iterdir() if path.is_dir()),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    for path in runs[keep:]:
        shutil.rmtree(path)


def _retention_settings() -> tuple[int, int]:
    """pyproject.tomlから保持件数と容量上限を取得する。"""
    try:
        with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as stream:
            quality = tomllib.load(stream)["tool"]["werewolf-quality"]
        count = int(quality["failure_runs_per_selector"])
        limit = int(quality["failure_run_max_mib"]) * 1024 * 1024
    except (KeyError, OSError, TypeError, ValueError, tomllib.TOMLDecodeError):
        return FAILURES_PER_SELECTOR, FAILURE_BYTES_LIMIT
    if count < 1 or limit < 1:
        return FAILURES_PER_SELECTOR, FAILURE_BYTES_LIMIT
    return count, limit


@contextmanager
def _publication_lock() -> Iterator[None]:
    """成果物確定とretentionの短い区間だけprocess間lockを取得する。"""
    LAYOUT.quality.mkdir(parents=True, exist_ok=True)
    lock_path = LAYOUT.quality / ".publish.lock"
    deadline = time.monotonic() + 10
    while True:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"{os.getpid()}\n".encode())
            os.close(descriptor)
            break
        except FileExistsError:
            try:
                stale = time.time() - lock_path.stat().st_mtime > 60
            except FileNotFoundError:
                continue
            if stale:
                lock_path.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError("品質成果物の公開lockを取得できませんでした。") from None
            time.sleep(0.05)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _replace_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


__all__ = ["FAILURES_PER_SELECTOR", "FAILURE_BYTES_LIMIT", "publish_run"]
