"""変更pathから安全側の品質実行範囲を決定する。"""

from __future__ import annotations

import fnmatch
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from scripts._infra.process import REPOSITORY_ROOT

POLICY_PATH = Path(__file__).with_name("impact.toml")
PROFILE_ORDER = ("focus", "check", "release", "deep")


@dataclass(frozen=True, slots=True)
class ImpactDecision:
    """変更影響から選択したprofileとgate。"""

    profile: str
    selectors: tuple[str, ...] = ()
    changed_paths: tuple[str, ...] = ()
    reason: str = ""


def changed_paths() -> tuple[str, ...]:
    """HEADとの差分と未追跡fileをrepository相対pathで返す。"""
    commands = (
        ("git", "diff", "--name-only", "HEAD"),
        ("git", "ls-files", "--others", "--exclude-standard"),
    )
    paths: set[str] = set()
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            raise RuntimeError("変更影響を判定するGit情報を取得できません。")
        paths.update(line.strip().replace("\\", "/") for line in completed.stdout.splitlines())
    return tuple(sorted(path for path in paths if path))


def decide(paths: tuple[str, ...] | None = None) -> ImpactDecision:
    """未知pathをcheckへ昇格する保守的な影響判定を返す。"""
    selected_paths = changed_paths() if paths is None else paths
    if not selected_paths:
        return ImpactDecision("focus", reason="変更差分がないためfocus一式を実行します。")
    with POLICY_PATH.open("rb") as stream:
        rules = tomllib.load(stream).get("rules")
    if not isinstance(rules, list):
        raise ValueError("変更影響rulesを配列で定義してください。")
    selectors: set[str] = set()
    profile = "focus"
    unknown: list[str] = []
    for path in selected_paths:
        matches = [rule for rule in rules if _matches(rule, path)]
        if not matches:
            unknown.append(path)
            continue
        for rule in matches:
            declared_profile = rule.get("profile", "focus")
            if not isinstance(declared_profile, str) or declared_profile not in PROFILE_ORDER:
                raise ValueError(f"変更影響profileが不正です: {declared_profile}")
            profile = max((profile, declared_profile), key=PROFILE_ORDER.index)
            declared_selectors = rule.get("selectors", [])
            if not isinstance(declared_selectors, list) or not all(
                isinstance(value, str) for value in declared_selectors
            ):
                raise ValueError("変更影響selectorは文字列配列で定義してください。")
            selectors.update(declared_selectors)
    if unknown:
        profile = max((profile, "check"), key=PROFILE_ORDER.index)
    if profile != "focus":
        selectors.clear()
    reason = f"{len(selected_paths)}件の変更を影響policyで{profile}へ割り当てました。"
    if unknown:
        reason += " 未登録pathは最低checkとして扱います: " + ", ".join(unknown)
    return ImpactDecision(
        profile,
        tuple(sorted(selectors)),
        selected_paths,
        reason,
    )


def _matches(rule: object, path: str) -> bool:
    if not isinstance(rule, dict):
        raise ValueError("変更影響ruleをTOML tableとして定義してください。")
    patterns = rule.get("patterns")
    if not isinstance(patterns, list) or not all(isinstance(value, str) for value in patterns):
        raise ValueError("変更影響patternsは文字列配列で定義してください。")
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


__all__ = ["ImpactDecision", "changed_paths", "decide"]
