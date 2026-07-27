"""Repository内の成果物配置を一元管理する。"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from scripts._infra.process import ARTIFACT_ROOT, REPOSITORY_ROOT, TEMPORARY_ROOT


@dataclass(frozen=True, slots=True)
class ArtifactLayout:
    """開発・品質成果物の標準配置。"""

    root: Path = ARTIFACT_ROOT

    @property
    def cache(self) -> Path:
        """再利用可能なtool cacheの配置を返す。"""
        return self.root / "cache"

    @property
    def logs(self) -> Path:
        """Application logの配置を返す。"""
        return self.root / "logs"

    @property
    def operations(self) -> Path:
        """有限の開発操作が残すrun成果物の配置を返す。"""
        return self.root / "operations"

    @property
    def diagnostics(self) -> Path:
        """既存成果物から生成する診断viewの配置を返す。"""
        return self.root / "diagnostics"

    @property
    def quality(self) -> Path:
        """品質reportの配置を返す。"""
        return self.root / "quality"

    @property
    def reviews(self) -> Path:
        """人間またはAIによるreview成果物の配置を返す。"""
        return self.root / "reviews"

    @property
    def outputs(self) -> Path:
        """文書、構造分析、package生成物の配置を返す。"""
        return self.root / "outputs"

    @property
    def runtime(self) -> Path:
        """ローカルruntime状態の配置を返す。"""
        return self.root / "runtime"


LAYOUT = ArtifactLayout()


@contextmanager
def staged_directory(name: str) -> Iterator[Path]:
    """Repository内にbuild用scratch directoryを作成して必ず破棄する。"""
    root = TEMPORARY_ROOT / "build"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        if path.exists():
            shutil.rmtree(path)


def publish_directory(source: Path, target: Path) -> None:
    """検証済みdirectoryを既存成果物を壊さず短時間で置換する。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.with_name(f".{target.name}.backup")
    if backup.exists():
        shutil.rmtree(backup)
    if target.exists():
        target.replace(backup)
    try:
        source.replace(target)
    except BaseException:
        if backup.exists() and not target.exists():
            backup.replace(target)
        raise
    if backup.exists():
        shutil.rmtree(backup)


__all__ = [
    "ARTIFACT_ROOT",
    "LAYOUT",
    "REPOSITORY_ROOT",
    "TEMPORARY_ROOT",
    "ArtifactLayout",
    "publish_directory",
    "staged_directory",
]
