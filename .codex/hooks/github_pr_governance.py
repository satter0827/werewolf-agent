"""CodexによるGitHub PR判断操作を構造化入力で制御する。"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

HOOK_EVENT = "PreToolUse"
GITHUB_OPERATION_PREFIX = "github_"
ADD_REVIEW_OPERATION = "add_review_to_pr"
MERGE_OPERATION = "merge_pull_request"
DEVELOP_BRANCH = "develop"
MERGE_METHOD = "merge"
BLOCKED_OPERATIONS = frozenset(
    {
        "dismiss_pull_request_review",
        "enable_auto_merge",
        "resolve_review_thread",
        "unresolve_review_thread",
    }
)
FORMAL_REVIEW_ACTIONS = frozenset({"APPROVE", "REQUEST_CHANGES"})
ALLOWED_REVIEW_ACTIONS = frozenset({"COMMENT"})


@dataclass(frozen=True)
class PullRequestState:
    """判断操作に必要なGitHub上のPR状態。"""

    base_ref: str
    head_sha: str


def _deny(reason: str) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT,
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _github_operation(tool_name: str) -> str | None:
    if not tool_name.startswith("mcp__") or "__" not in tool_name:
        return None
    candidate = tool_name.rsplit("__", maxsplit=1)[-1]
    if not candidate.startswith(GITHUB_OPERATION_PREFIX):
        return None
    return candidate.removeprefix(GITHUB_OPERATION_PREFIX)


def _pull_request_number(tool_input: Mapping[str, object]) -> int | None:
    return next(
        (
            value
            for key in ("pr_number", "pull_number")
            if isinstance((value := tool_input.get(key)), int) and not isinstance(value, bool)
        ),
        None,
    )


def _repository(tool_input: Mapping[str, object]) -> str | None:
    repository = next(
        (
            value.strip()
            for key in ("repository_full_name", "repo_full_name")
            if isinstance((value := tool_input.get(key)), str) and value.strip()
        ),
        None,
    )
    if repository is not None:
        return repository
    owner = tool_input.get("owner")
    repo = tool_input.get("repo")
    if isinstance(owner, str) and owner.strip() and isinstance(repo, str) and repo.strip():
        return f"{owner.strip()}/{repo.strip()}"
    return None


def _pull_request_state(tool_input: Mapping[str, object]) -> PullRequestState | None:
    """GitHubからPRのbaseと最新head SHAをread-onlyで解決する。"""
    number = _pull_request_number(tool_input)
    repository = _repository(tool_input)
    if number is None or repository is None:
        return None
    command = ["gh", "pr", "view", str(number), "--json", "baseRefName,headRefOid"]
    command.extend(("--repo", repository))
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    try:
        document = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(document, Mapping):
        return None
    base_ref = document.get("baseRefName")
    head_sha = document.get("headRefOid")
    if not isinstance(base_ref, str) or not base_ref.strip():
        return None
    if not isinstance(head_sha, str) or not head_sha.strip():
        return None
    return PullRequestState(base_ref=base_ref.strip(), head_sha=head_sha.strip())


def _normalized_string(tool_input: Mapping[str, object], key: str) -> str | None:
    value = tool_input.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _evaluate_review(tool_input: object) -> dict[str, object] | None:
    if not isinstance(tool_input, Mapping):
        return _deny("レビュー入力を確認できないため、操作を拒否します。")
    action = _normalized_string(tool_input, "action")
    if action is None:
        return _deny("レビュー種別を確認できないため、操作を拒否します。")
    normalized_action = action.upper()
    if normalized_action in ALLOWED_REVIEW_ACTIONS:
        return None
    if normalized_action not in FORMAL_REVIEW_ACTIONS:
        return _deny("未知のレビュー種別は許可しません。COMMENTとして助言してください。")

    state = _pull_request_state(tool_input)
    commit_id = _normalized_string(tool_input, "commit_id")
    if state is None or state.base_ref != DEVELOP_BRANCH:
        return _deny("AIはdevelop以外のPRへ正式なレビュー判断を送信しません。")
    if commit_id is None or commit_id != state.head_sha:
        return _deny("developの正式レビューは最新head SHAへ固定してください。")
    return None


def _evaluate_merge(tool_input: object) -> dict[str, object] | None:
    if not isinstance(tool_input, Mapping):
        return _deny("merge入力を確認できないため、操作を拒否します。")
    state = _pull_request_state(tool_input)
    merge_method = _normalized_string(tool_input, "merge_method")
    expected_head_sha = _normalized_string(tool_input, "expected_head_sha")
    if state is None or state.base_ref != DEVELOP_BRANCH:
        return _deny("AIはdevelop向けPRだけをmerge commitで取り込みます。")
    if merge_method is None or merge_method.casefold() != MERGE_METHOD:
        return _deny("develop向けPRはmerge commitで取り込んでください。")
    if expected_head_sha is None or expected_head_sha != state.head_sha:
        return _deny("developのmergeは最新head SHAをexpected_head_shaへ指定してください。")
    return None


def evaluate(payload: Mapping[str, object]) -> dict[str, object] | None:
    """hook入力を評価し、拒否時だけCodex hook応答を返す。"""
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_name, str):
        return _deny("PRガバナンスhookが対象ツールを識別できません。人間へ引き渡してください。")

    operation = _github_operation(tool_name)
    if operation == ADD_REVIEW_OPERATION:
        return _evaluate_review(tool_input)
    if operation == MERGE_OPERATION:
        return _evaluate_merge(tool_input)
    if operation in BLOCKED_OPERATIONS:
        return _deny(
            "AIはレビュー却下、会話解決、auto-mergeを実行しません。対象PRを人間へ引き渡してください。"
        )
    return None


def main() -> int:
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    result: dict[str, object] | None
    try:
        payload: object = json.load(sys.stdin)
        if not isinstance(payload, Mapping):
            result = _deny("PRガバナンスhookの入力形式が不正なため、操作を拒否します。")
        else:
            result = evaluate(cast(Mapping[str, object], payload))
    except (json.JSONDecodeError, UnicodeDecodeError):
        result = _deny("PRガバナンスhookの入力を解析できないため、操作を拒否します。")
    except Exception:
        result = _deny("PRガバナンスhookを評価できないため、操作を拒否します。")
    if result is not None:
        json.dump(result, sys.stdout, ensure_ascii=False, separators=(",", ":"))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
