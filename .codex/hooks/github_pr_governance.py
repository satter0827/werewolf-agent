"""CodexからGitHub PRの正式な判断操作を実行できないようにする。"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from typing import cast

HOOK_EVENT = "PreToolUse"
GITHUB_OPERATION_PREFIX = "github_"
ADD_REVIEW_OPERATION = "add_review_to_pr"
BLOCKED_OPERATIONS = frozenset(
    {
        "dismiss_pull_request_review",
        "enable_auto_merge",
        "merge_pull_request",
        "resolve_review_thread",
        "unresolve_review_thread",
    }
)
BLOCKED_REVIEW_ACTIONS = frozenset({"APPROVE", "REQUEST_CHANGES"})
ALLOWED_REVIEW_ACTIONS = frozenset({"COMMENT"})

_GH_INVOCATION = re.compile(
    r"(?:"
    r"^\s*(?:&\s*)?"
    r"|[;&|]\s*(?:&\s*)?"
    r"|\b(?:powershell|pwsh)(?:\.exe)?\b[^\r\n]*?"
    r"(?:-Command|-c)\s+[\"']?\s*(?:&\s*)?"
    r")"
    r"gh(?:\.exe)?\s+(?P<arguments>[^;\r\n|&]+)",
    re.IGNORECASE | re.MULTILINE,
)
_BLOCKED_API_WRITE = re.compile(
    r"(?:"
    r"(?:event|action)(?:\]|[\s:=\"'])*(?:approve|request[_-]changes)\b"
    r"|/pulls/(?:\d+|\$\{?[^\s/}]+\}?)/merge\b"
    r"|/pulls/(?:\d+|\$\{?[^\s/}]+\}?)/reviews/[^\s/]+/dismissals\b"
    r"|addpullrequestreview\b[^\r\n]*(?:approve|request_changes)"
    r"|dismisspullrequestreview\b"
    r"|enablepullrequestautomerge\b"
    r"|mergepullrequest\b"
    r"|resolve(?:pullrequest)?reviewthread\b"
    r"|unresolve(?:pullrequest)?reviewthread\b"
    r")",
    re.IGNORECASE,
)


def _deny(reason: str) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT,
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _command_from(tool_input: object) -> str | None:
    if not isinstance(tool_input, Mapping):
        return None
    command = tool_input.get("command")
    return command if isinstance(command, str) else None


def _github_operation(tool_name: str) -> str | None:
    if not tool_name.startswith("mcp__") or "__" not in tool_name:
        return None
    candidate = tool_name.rsplit("__", maxsplit=1)[-1]
    if not candidate.startswith(GITHUB_OPERATION_PREFIX):
        return None
    return candidate.removeprefix(GITHUB_OPERATION_PREFIX)


def _blocked_shell_operation(command: str) -> bool:
    for match in _GH_INVOCATION.finditer(command):
        arguments = match.group("arguments").strip().strip("\"'")
        normalized = re.sub(r"\s+", " ", arguments).casefold()
        if re.match(r"^pr merge(?:\s|$)", normalized):
            return True
        if re.match(r"^pr review(?:\s|$)", normalized):
            tokens = {token.strip("\"',") for token in normalized.split()}
            if tokens.intersection({"--approve", "-a", "--request-changes", "-r"}):
                return True
        if re.match(r"^api(?:\s|$)", normalized) and _BLOCKED_API_WRITE.search(arguments):
            return True
    return False


def evaluate(payload: Mapping[str, object]) -> dict[str, object] | None:
    """hook入力を評価し、拒否時だけCodex hook応答を返す。"""
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_name, str):
        return _deny("PRガバナンスhookが対象ツールを識別できません。人間へ引き渡してください。")

    operation = _github_operation(tool_name)
    if operation == ADD_REVIEW_OPERATION:
        if not isinstance(tool_input, Mapping):
            return _deny("レビュー種別を確認できないため、正式なレビュー操作を拒否します。")
        action = tool_input.get("action")
        if not isinstance(action, str):
            return _deny("レビュー種別を確認できないため、正式なレビュー操作を拒否します。")
        normalized_action = action.strip().upper()
        if normalized_action in ALLOWED_REVIEW_ACTIONS:
            return None
        if normalized_action in BLOCKED_REVIEW_ACTIONS:
            return _deny(
                "AIはAPPROVEまたはREQUEST_CHANGESを送信しません。対象PRを人間へ引き渡してください。"
            )
        return _deny("未知のレビュー種別は許可しません。COMMENTとして助言してください。")

    if operation in BLOCKED_OPERATIONS:
        return _deny(
            "AIはレビュー却下、会話解決、auto-merge、mergeを実行しません。対象PRを人間へ引き渡してください。"
        )

    if tool_name != "Bash":
        return None
    command = _command_from(tool_input)
    if command is None:
        return _deny("shell commandを確認できないため、PRガバナンスhookが実行を拒否します。")
    if _blocked_shell_operation(command):
        return _deny("AIはgh経由の正式なレビュー判断、会話解決、auto-merge、mergeを実行しません。")
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
