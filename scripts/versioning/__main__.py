"""Version所有境界を検査・更新するcommand line入口。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from functools import total_ordering
from pathlib import Path
from typing import Literal, cast

from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path(__file__).with_name("registry.toml")
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
CONVENTIONAL_SUBJECT = re.compile(
    r"^(?P<type>[A-Za-z][A-Za-z0-9-]*)(?:\([^\r\n)]+\))?(?P<breaking>!)?:"
)
BREAKING_FOOTER = re.compile(r"^BREAKING(?: CHANGE|-CHANGE):", re.MULTILINE)

VersionLevel = Literal["patch", "minor", "major"]
VersionStandard = Literal["pep440", "semver"]


@dataclass(frozen=True, slots=True)
class Boundary:
    """1つのversion所有境界。"""

    name: str
    owner: str
    standard: VersionStandard
    path: str
    pattern: str
    watch: tuple[str, ...]


@total_ordering
@dataclass(frozen=True, slots=True)
class SemanticVersion:
    """SemVer 2.0.0のprecedenceを表す。"""

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] | None = None

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        core = (self.major, self.minor, self.patch)
        other_core = (other.major, other.minor, other.patch)
        if core != other_core:
            return core < other_core
        if self.prerelease is None:
            return False
        if other.prerelease is None:
            return True
        for left, right in zip(self.prerelease, other.prerelease, strict=False):
            if left == right:
                continue
            left_numeric = left.isdigit()
            right_numeric = right.isdigit()
            if left_numeric and right_numeric:
                return int(left) < int(right)
            if left_numeric != right_numeric:
                return left_numeric
            return left < right
        return len(self.prerelease) < len(other.prerelease)


def _boundaries() -> tuple[Boundary, ...]:
    with REGISTRY.open("rb") as stream:
        items = tomllib.load(stream)["boundaries"]
    standards = {"pep440", "semver"}
    unknown = {str(item["standard"]) for item in items if str(item["standard"]) not in standards}
    if unknown:
        raise ValueError(f"未定義のversion規格です: {', '.join(sorted(unknown))}")
    return tuple(
        Boundary(
            name=str(item["name"]),
            owner=str(item["owner"]),
            standard=cast(VersionStandard, str(item["standard"])),
            path=str(item["path"]),
            pattern=str(item["pattern"]),
            watch=tuple(str(path) for path in item["watch"]),
        )
        for item in items
    )


def _semantic_version(value: str) -> SemanticVersion:
    match = SEMVER.fullmatch(value)
    if match is None:
        raise ValueError(f"SemVerではありません: {value}")
    prerelease = tuple(match.group(4).split(".")) if match.group(4) else None
    if prerelease is not None and any(
        item.isdigit() and len(item) > 1 and item.startswith("0") for item in prerelease
    ):
        raise ValueError(f"SemVerではありません: {value}")
    return SemanticVersion(
        int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease
    )


def _validated_version(boundary: Boundary, value: str) -> str:
    if boundary.standard == "semver":
        _semantic_version(value)
        return value
    if boundary.standard != "pep440":
        raise ValueError(f"{boundary.name}: 未定義のversion規格です: {boundary.standard}")
    try:
        Version(value)
    except InvalidVersion as error:
        raise ValueError(f"{boundary.name}: PEP 440ではありません: {value}") from error
    return value


def _version(boundary: Boundary, content: str) -> str:
    match = re.search(boundary.pattern, content)
    if match is None:
        raise ValueError(f"{boundary.name}: versionを{boundary.path}から取得できません。")
    return _validated_version(boundary, match.group(1))


def _repository_path(relative_path: str) -> Path:
    root = ROOT.resolve()
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"repository外のversion pathです: {relative_path}")
    return target


def inspect() -> list[dict[str, object]]:
    """現在のversion registryを返す。"""
    return [
        {
            "name": boundary.name,
            "owner": boundary.owner,
            "standard": boundary.standard,
            "version": _version(
                boundary, _repository_path(boundary.path).read_text(encoding="utf-8")
            ),
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


def _merge_base(base_ref: str, head_ref: str) -> str:
    value = _git("merge-base", base_ref, head_ref, allow_failure=True)
    if value is None:
        raise ValueError(f"base refを解決できません: {base_ref}")
    return value.strip()


def _changed_paths(base_ref: str, head_ref: str) -> tuple[str, ...]:
    base_revision = _merge_base(base_ref, head_ref)
    if head_ref == "HEAD":
        changed_output = _git("diff", "--name-only", base_revision) or ""
        untracked_output = _git("ls-files", "--others", "--exclude-standard") or ""
        changed_output += untracked_output
    else:
        changed_output = _git("diff", "--name-only", f"{base_revision}..{head_ref}") or ""
    return tuple(
        sorted(
            {
                line.strip().replace("\\", "/")
                for line in changed_output.splitlines()
                if line.strip()
            }
        )
    )


def _matches_watch(path: str, watched: str) -> bool:
    normalized = watched.replace("\\", "/")
    return path.startswith(normalized) if normalized.endswith("/") else path == normalized


def _touched(boundary: Boundary, changed: Sequence[str]) -> bool:
    return any(_matches_watch(path, watched) for path in changed for watched in boundary.watch)


def _compare(boundary: Boundary, left: str, right: str) -> int:
    if boundary.standard == "pep440":
        left_value: Version | SemanticVersion = Version(left)
        right_value: Version | SemanticVersion = Version(right)
    else:
        left_value = _semantic_version(left)
        right_value = _semantic_version(right)
    return (left_value > right_value) - (left_value < right_value)


def _base_version(boundary: Boundary, base_revision: str) -> str | None:
    content = _git("show", f"{base_revision}:{boundary.path}", allow_failure=True)
    if content is None:
        return None
    return _version(boundary, content)


def _current_version(boundary: Boundary, head_ref: str) -> str:
    content: str | None
    if head_ref == "HEAD":
        content = _repository_path(boundary.path).read_text(encoding="utf-8")
    else:
        content = _git("show", f"{head_ref}:{boundary.path}", allow_failure=True)
    if content is None:
        raise ValueError(f"{boundary.name}: {head_ref}に{boundary.path}がありません。")
    return _version(boundary, content)


def check(base_ref: str, head_ref: str) -> list[str]:
    """変更された境界がversion更新を伴うことを検査する。"""
    try:
        base_revision = _merge_base(base_ref, head_ref)
        changed = _changed_paths(base_ref, head_ref)
    except ValueError as error:
        return [str(error)]
    issues: list[str] = []
    for boundary in _boundaries():
        current_version = _current_version(boundary, head_ref)
        base_version = _base_version(boundary, base_revision)
        if base_version is None:
            continue
        comparison = _compare(boundary, current_version, base_version)
        if comparison < 0:
            issues.append(
                f"{boundary.name}: versionが退行しています: {base_version} -> {current_version}"
            )
        elif _touched(boundary, changed) and comparison == 0:
            issues.append(
                f"{boundary.name}: 所有範囲が変更されていますが"
                f"versionは{current_version}のままです。"
            )
    return issues


def _bumped_version(boundary: Boundary, value: str, level: VersionLevel) -> str:
    if boundary.standard == "pep440":
        parsed_product = Version(value)
        release = parsed_product.release
        major, minor, patch = (*release, 0, 0, 0)[:3]
        prefix = f"{parsed_product.epoch}!" if parsed_product.epoch else ""
    else:
        parsed = _semantic_version(value)
        major, minor, patch = parsed.major, parsed.minor, parsed.patch
        prefix = ""
    if level == "major":
        return f"{prefix}{major + 1}.0.0"
    if level == "minor":
        return f"{prefix}{major}.{minor + 1}.0"
    return f"{prefix}{major}.{minor}.{patch + 1}"


def _replace_version(content: str, boundary: Boundary, new_version: str) -> str:
    match = re.search(boundary.pattern, content)
    if match is None:
        raise ValueError(f"{boundary.name}: versionを{boundary.path}から取得できません。")
    start, end = match.span(1)
    return f"{content[:start]}{new_version}{content[end:]}"


def bump(
    level: VersionLevel,
    base_ref: str,
    head_ref: str,
    *,
    dry_run: bool = False,
) -> list[dict[str, str]]:
    """変更pathが触れた境界を指定levelへ更新する。"""
    if head_ref != "HEAD":
        raise ValueError("bumpのhead refはHEADだけを指定できます。")
    base_revision = _merge_base(base_ref, head_ref)
    changed = _changed_paths(base_ref, head_ref)
    contents: dict[str, str] = {}
    updates: list[dict[str, str]] = []
    for boundary in _boundaries():
        if not _touched(boundary, changed):
            continue
        base_version = _base_version(boundary, base_revision)
        if base_version is None:
            continue
        path = _repository_path(boundary.path)
        content = contents.setdefault(boundary.path, path.read_text(encoding="utf-8"))
        current_version = _version(boundary, content)
        target_version = _bumped_version(boundary, base_version, level)
        if _compare(boundary, current_version, target_version) == 0:
            continue
        if _compare(boundary, current_version, base_version) != 0:
            raise ValueError(
                f"{boundary.name}: {current_version}は基準{base_version}とも"
                f"更新先{target_version}とも一致しません。"
            )
        contents[boundary.path] = _replace_version(content, boundary, target_version)
        updates.append(
            {
                "name": boundary.name,
                "path": boundary.path,
                "before": current_version,
                "after": target_version,
            }
        )
    if not dry_run:
        for relative_path, content in contents.items():
            _repository_path(relative_path).write_text(content, encoding="utf-8", newline="")
    return updates


def _suggest_level(messages: Sequence[str]) -> tuple[VersionLevel, str]:
    for message in messages:
        subject = message.splitlines()[0] if message.splitlines() else ""
        match = CONVENTIONAL_SUBJECT.match(subject)
        if (match is not None and match.group("breaking")) or BREAKING_FOOTER.search(message):
            return "major", "破壊的変更のmarkerを検出しました。"
    for message in messages:
        subject = message.splitlines()[0] if message.splitlines() else ""
        match = CONVENTIONAL_SUBJECT.match(subject)
        if match is not None and match.group("type").lower() == "feat":
            return "minor", "feat commitを検出しました。"
    return "patch", "破壊的変更とfeat commitを検出しませんでした。"


def suggest(base_ref: str, head_ref: str) -> tuple[VersionLevel, str]:
    """Conventional Commitから変更levelを提案する。"""
    base_revision = _merge_base(base_ref, head_ref)
    output = _git("log", "--format=%s%n%b%x00", f"{base_revision}..{head_ref}") or ""
    messages = tuple(item.strip() for item in output.split("\x00") if item.strip())
    return _suggest_level(messages)


def _add_refs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--head-ref", default="HEAD")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Version所有境界を管理する。")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--json", action="store_true")
    check_parser = subparsers.add_parser("check")
    _add_refs(check_parser)
    suggest_parser = subparsers.add_parser("suggest")
    _add_refs(suggest_parser)
    bump_parser = subparsers.add_parser("bump")
    bump_parser.add_argument("level", choices=("patch", "minor", "major"))
    _add_refs(bump_parser)
    bump_parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "inspect":
            document = inspect()
            if arguments.json:
                print(json.dumps(document, ensure_ascii=False, indent=2))
            else:
                for entry in document:
                    print(
                        f"{entry['name']}: {entry['version']} "
                        f"({entry['standard']}, {entry['owner']})"
                    )
            return 0
        if arguments.command == "check":
            issues = check(arguments.base_ref, arguments.head_ref)
            if issues:
                print("\n".join(f"- {issue}" for issue in issues))
                return 1
            print("version contract passed")
            return 0
        if arguments.command == "suggest":
            level, reason = suggest(arguments.base_ref, arguments.head_ref)
            print(f"suggested level: {level}")
            print(reason)
            return 0
        updates = bump(
            arguments.level,
            arguments.base_ref,
            arguments.head_ref,
            dry_run=arguments.dry_run,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}")
        return 1
    if not updates:
        print("更新対象のversionはありません。")
        return 0
    prefix = "would update" if arguments.dry_run else "updated"
    for update in updates:
        print(
            f"{prefix}: {update['name']} {update['before']} -> {update['after']} ({update['path']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
