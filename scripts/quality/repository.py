"""Git repositoryの検証対象と不変snapshotを取得する。"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts._infra.process import REPOSITORY_ROOT


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    """品質実行前後で比較するrepository状態。"""

    revision: str
    tree: str
    index_tree: str
    dirty: bool
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ChangeSet:
    """baseとheadから解決した変更範囲。"""

    base_ref: str | None
    base_revision: str | None
    head_revision: str
    merge_base_revision: str | None
    changed_paths: tuple[str, ...]
    head_ref: str = "HEAD"


def resolve_changes(
    base_ref: str | None,
    head_ref: str = "HEAD",
    *,
    root: Path = REPOSITORY_ROOT,
) -> ChangeSet:
    """commit差分と現在のworkspace差分を統合する。"""
    head_revision = _git_text(root, "rev-parse", "--verify", f"{head_ref}^{{commit}}")
    base_revision: str | None = None
    merge_base_revision: str | None = None
    paths: set[str] = set()
    if base_ref is not None:
        base_revision = _git_text(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
        merge_base_revision = _git_text(root, "merge-base", base_revision, head_revision)
        paths.update(
            _git_lines(root, "diff", "--name-only", merge_base_revision, head_revision, "--")
        )
    paths.update(_git_lines(root, "diff", "--name-only", "HEAD"))
    paths.update(_untracked_paths(root))
    return ChangeSet(
        base_ref=base_ref,
        base_revision=base_revision,
        head_revision=head_revision,
        merge_base_revision=merge_base_revision,
        changed_paths=tuple(sorted(paths)),
        head_ref=head_ref,
    )


def capture_snapshot(*, root: Path = REPOSITORY_ROOT) -> RepositorySnapshot:
    """tracked状態と非ignoreの未追跡fileを含む決定的snapshotを返す。"""
    revision = _git_text(root, "rev-parse", "--verify", "HEAD^{commit}")
    tree = _git_text(root, "rev-parse", "--verify", "HEAD^{tree}")
    index_tree = _git_text(root, "write-tree")
    status = _git_bytes(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    digest = hashlib.sha256()
    for label, value in (
        (b"revision", revision.encode()),
        (b"tree", tree.encode()),
        (b"index", index_tree.encode()),
        (b"status", status),
        (b"diff", _git_bytes(root, "diff", "--binary", "HEAD")),
    ):
        digest.update(label + b"\0" + value + b"\0")
    for relative in _untracked_paths(root):
        digest.update(b"untracked\0" + relative.encode("utf-8") + b"\0")
        digest.update((root / relative).read_bytes())
        digest.update(b"\0")
    return RepositorySnapshot(
        revision=revision,
        tree=tree,
        index_tree=index_tree,
        dirty=bool(status),
        fingerprint=digest.hexdigest(),
    )


def _untracked_paths(root: Path) -> tuple[str, ...]:
    return tuple(sorted(_git_lines(root, "ls-files", "--others", "--exclude-standard")))


def _git_lines(root: Path, *arguments: str) -> tuple[str, ...]:
    output = _git_bytes(root, *arguments).decode("utf-8", errors="replace")
    return tuple(line.strip().replace("\\", "/") for line in output.splitlines() if line.strip())


def _git_text(root: Path, *arguments: str) -> str:
    return _git_bytes(root, *arguments).decode("utf-8", errors="replace").strip()


def _git_bytes(root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=root,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Git repository情報を取得できません: {message or arguments[0]}")
    return completed.stdout


__all__ = ["ChangeSet", "RepositorySnapshot", "capture_snapshot", "resolve_changes"]
