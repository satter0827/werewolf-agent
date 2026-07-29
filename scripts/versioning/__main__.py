"""SemVer境界を検査するcommand line入口。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path(__file__).with_name("registry.toml")
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


@dataclass(frozen=True, slots=True)
class Boundary:
    """1つのversion所有境界。"""

    name: str
    owner: str
    path: str
    pattern: str
    watch: tuple[str, ...]


def _boundaries() -> tuple[Boundary, ...]:
    with REGISTRY.open("rb") as stream:
        items = tomllib.load(stream)["boundaries"]
    return tuple(
        Boundary(
            name=str(item["name"]),
            owner=str(item["owner"]),
            path=str(item["path"]),
            pattern=str(item["pattern"]),
            watch=tuple(str(path) for path in item["watch"]),
        )
        for item in items
    )


def _version(boundary: Boundary, content: str) -> str:
    match = re.search(boundary.pattern, content)
    if match is None:
        raise ValueError(f"{boundary.name}: versionを{boundary.path}から取得できません。")
    value = match.group(1)
    if SEMVER.fullmatch(value) is None:
        raise ValueError(f"{boundary.name}: SemVerではありません: {value}")
    return value


def inspect() -> list[dict[str, object]]:
    """現在のversion registryを返す。"""
    return [
        {
            "name": boundary.name,
            "owner": boundary.owner,
            "version": _version(boundary, (ROOT / boundary.path).read_text(encoding="utf-8")),
            "watch": list(boundary.watch),
        }
        for boundary in _boundaries()
    ]


def _git(*arguments: str, allow_failure: bool = False) -> str | None:
    result = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode == 0:
        return result.stdout
    if allow_failure:
        return None
    raise RuntimeError(result.stderr.strip() or "git command failed")


def _version_key(value: str) -> tuple[int, int, int, int]:
    match = SEMVER.fullmatch(value)
    if match is None:
        raise ValueError(value)
    prerelease_rank = 0 if match.group(4) is not None else 1
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease_rank


def check(base_ref: str, head_ref: str) -> list[str]:
    """変更された境界がversion更新を伴うことを検査する。"""
    issues: list[str] = []
    current = {item["name"]: item for item in inspect()}
    merge_base = _git("merge-base", base_ref, head_ref, allow_failure=True)
    if merge_base is None:
        return [f"base refを解決できません: {base_ref}"]
    base_revision = merge_base.strip()
    changed_output = _git("diff", "--name-only", f"{base_revision}..{head_ref}") or ""
    changed = tuple(line.strip().replace("\\", "/") for line in changed_output.splitlines())
    for boundary in _boundaries():
        current_version = str(current[boundary.name]["version"])
        base_content = _git("show", f"{base_revision}:{boundary.path}", allow_failure=True)
        if base_content is None:
            continue
        try:
            base_version = _version(boundary, base_content)
        except ValueError:
            continue
        if _version_key(current_version) < _version_key(base_version):
            issues.append(
                f"{boundary.name}: versionが退行しています: {base_version} -> {current_version}"
            )
        touched = any(
            path == watched.rstrip("/") or path.startswith(watched)
            for path in changed
            for watched in boundary.watch
        )
        if touched and current_version == base_version:
            issues.append(
                f"{boundary.name}: 所有範囲が変更されていますが"
                f"versionは{current_version}のままです。"
            )
    return issues


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SemVer境界を検査する。")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--json", action="store_true")
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--base-ref", default="origin/main")
    check_parser.add_argument("--head-ref", default="HEAD")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "inspect":
        document = inspect()
        if arguments.json:
            print(json.dumps(document, ensure_ascii=False, indent=2))
        else:
            for item in document:
                print(f"{item['name']}: {item['version']} ({item['owner']})")
        return 0
    issues = check(arguments.base_ref, arguments.head_ref)
    if issues:
        print("\n".join(f"- {issue}" for issue in issues))
        return 1
    print("version contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
