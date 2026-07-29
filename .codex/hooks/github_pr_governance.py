"""CodexによるGitHub PR判断操作をtarget branchごとに制御する。"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Mapping
from typing import cast

HOOK_EVENT = "PreToolUse"
GITHUB_OPERATION_PREFIX = "github_"
ADD_REVIEW_OPERATION = "add_review_to_pr"
MERGE_OPERATION = "merge_pull_request"
DEVELOP_BRANCH = "develop"
BLOCKED_OPERATIONS = frozenset(
    {
        "dismiss_pull_request_review",
        "enable_auto_merge",
        "resolve_review_thread",
        "unresolve_review_thread",
    }
)
BLOCKED_REVIEW_ACTIONS = frozenset({"APPROVE", "REQUEST_CHANGES"})
ALLOWED_REVIEW_ACTIONS = frozenset({"COMMENT"})

_GH_INVOCATION = re.compile(
    r"(?:"
    r"^\s*"
    r"|[;&|(]\s*"
    r"|\b(?:powershell|pwsh)(?:\.exe)?\b[^\r\n]*?"
    r"(?:-Command|-c)\s+[\"']?\s*"
    r"|\b(?:cmd(?:\.exe)?\s+/c|(?:ba)?sh\s+-c)\s+[\"']?\s*"
    r")"
    r"(?:env(?:\s+-\S+)*\s+)?"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=(?:\"[^\"]*\"|'[^']*'|\S+)\s+)*"
    r"(?:command\s+)?(?:&\s*)?"
    r"(?:gh(?:\.exe)?|[^\s;|&\"']*[\\/]gh(?:\.exe)?|[\"'][^\"'\r\n]*[\\/]gh(?:\.exe)?[\"'])"
    r"\s+(?P<arguments>[^;\r\n|&]+)",
    re.IGNORECASE | re.MULTILINE,
)
_GH_ROOT_OPTION = re.compile(
    r"^(?:"
    r"(?:-R|--repo|--hostname)\s+(?:\"[^\"]*\"|'[^']*'|\S+)"
    r"|(?:--repo|--hostname)=\S+"
    r")\s+",
    re.IGNORECASE,
)
_GH_REPOSITORY_OPTION = re.compile(
    r"(?:^|\s)(?:-R|--repo)(?:\s+|=)(?P<repository>\"[^\"]*\"|'[^']*'|\S+)",
    re.IGNORECASE,
)
_HTTP_METHOD = re.compile(
    r"(?:^|\s)(?:-X(?:\s*|=)|--method(?:\s+|=))"
    r"(?P<method>GET|POST|PUT|PATCH|DELETE)\b",
    re.IGNORECASE,
)
_API_FIELD = re.compile(
    r"(?:^|\s)(?:(?:-f|-F)(?:\s*|=)|(?:--field|--raw-field)(?:\s+|=))"
    r"[\"']?(?P<name>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>[^\s\"']+)",
    re.IGNORECASE,
)
_REVIEW_COLLECTION = re.compile(
    r"/pulls/[^/\s?\"']+/reviews(?=\?|\s|[\"']|$)",
    re.IGNORECASE,
)
_REVIEW_SUBMISSION = re.compile(
    r"/pulls/[^/\s?\"']+/reviews/[^/\s?\"']+/events(?=\?|\s|[\"']|$)",
    re.IGNORECASE,
)
_REVIEW_DISMISSAL = re.compile(
    r"/pulls/[^/\s?\"']+/reviews/[^/\s?\"']+/dismissals(?:\b|\?)",
    re.IGNORECASE,
)
_MERGE_ENDPOINT = re.compile(
    r"/pulls/[^/\s?\"']+/merge(?:\b|\?)",
    re.IGNORECASE,
)
_BLOCKED_GRAPHQL_MUTATION = re.compile(
    r"\b(?:"
    r"dismissPullRequestReview"
    r"|enablePullRequestAutoMerge"
    r"|mergePullRequest"
    r"|resolveReviewThread"
    r"|unresolveReviewThread"
    r")\b",
    re.IGNORECASE,
)
_REVIEW_GRAPHQL_MUTATION = re.compile(
    r"\b(?:addPullRequestReview|submitPullRequestReview)\b",
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


def _pull_request_base(tool_input: Mapping[str, object]) -> str | None:
    """GitHubからPRのbase branchをread-onlyで解決する。"""
    number = next(
        (
            value
            for key in ("pr_number", "pull_number")
            if isinstance((value := tool_input.get(key)), int)
        ),
        None,
    )
    if number is None:
        return None
    repository = next(
        (
            value
            for key in ("repository_full_name", "repo_full_name")
            if isinstance((value := tool_input.get(key)), str) and value.strip()
        ),
        None,
    )
    if repository is None:
        owner = tool_input.get("owner")
        repo = tool_input.get("repo")
        if isinstance(owner, str) and owner.strip() and isinstance(repo, str) and repo.strip():
            repository = f"{owner.strip()}/{repo.strip()}"
    command = ["gh", "pr", "view", str(number), "--json", "baseRefName", "--jq", ".baseRefName"]
    if repository is not None:
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
    base = completed.stdout.strip()
    return base or None


def _is_develop_pull_request(tool_input: object) -> bool:
    return isinstance(tool_input, Mapping) and _pull_request_base(tool_input) == DEVELOP_BRANCH


def _without_gh_root_options(arguments: str) -> str:
    normalized = re.sub(r"\s+", " ", arguments.strip().strip("\"'")).strip()
    while match := _GH_ROOT_OPTION.match(normalized):
        normalized = normalized[match.end() :]
    return normalized


def _gh_repository(arguments: str) -> str | None:
    match = _GH_REPOSITORY_OPTION.search(arguments)
    if match is None:
        return None
    repository = match.group("repository").strip("\"'").strip()
    return repository or None


def _api_method(arguments: str) -> str:
    if match := _HTTP_METHOD.search(arguments):
        return match.group("method").upper()
    if _API_FIELD.search(arguments) or re.search(
        r"(?:^|\s)--input(?:\s+|=)", arguments, re.IGNORECASE
    ):
        return "POST"
    return "GET"


def _review_action(arguments: str) -> str | None:
    actions = {
        match.group("value").strip().upper().replace("-", "_")
        for match in _API_FIELD.finditer(arguments)
        if match.group("name").casefold() in {"action", "event"}
    }
    if len(actions) != 1:
        return None
    return actions.pop()


def _blocked_api_operation(arguments: str) -> bool:
    method = _api_method(arguments)
    is_write = method != "GET"
    is_graphql = bool(re.search(r"(?:^|\s)graphql(?:\s|$)", arguments, re.IGNORECASE))
    if is_write and (_MERGE_ENDPOINT.search(arguments) or _REVIEW_DISMISSAL.search(arguments)):
        return True
    if is_write and (_REVIEW_SUBMISSION.search(arguments) or _REVIEW_COLLECTION.search(arguments)):
        return _review_action(arguments) != "COMMENT"
    if is_graphql and _BLOCKED_GRAPHQL_MUTATION.search(arguments):
        return True
    if is_graphql and _REVIEW_GRAPHQL_MUTATION.search(arguments):
        return _review_action(arguments) != "COMMENT"
    if re.search(r"(?:^|\s)--input(?:\s+|=)", arguments, re.IGNORECASE):
        return is_graphql
    if re.search(r"(?:^|\s)(?:-f|-F|--field)(?:\s+|=)query=@", arguments, re.IGNORECASE):
        return is_graphql
    return False


def _shell_pull_request_input(
    arguments: str,
    repository: str | None,
) -> dict[str, object] | None:
    match = re.match(r"^pr\s+(?:merge|review)\s+(?P<number>\d+)(?:\s|$)", arguments, re.IGNORECASE)
    if match is None:
        return None
    tool_input: dict[str, object] = {"pr_number": int(match.group("number"))}
    if repository is not None:
        tool_input["repository_full_name"] = repository
    return tool_input


def _blocked_shell_operation(command: str) -> bool:
    for match in _GH_INVOCATION.finditer(command):
        raw_arguments = match.group("arguments")
        repository = _gh_repository(raw_arguments)
        arguments = _without_gh_root_options(raw_arguments)
        normalized = arguments.casefold()
        if re.match(r"^pr merge(?:\s|$)", normalized):
            pull_request = _shell_pull_request_input(arguments, repository)
            return pull_request is None or not _is_develop_pull_request(pull_request)
        if re.match(r"^pr review(?:\s|$)", normalized):
            tokens = {token.strip("\"',") for token in normalized.split()}
            if tokens.intersection({"--approve", "-a", "--request-changes", "-r"}):
                pull_request = _shell_pull_request_input(arguments, repository)
                return pull_request is None or not _is_develop_pull_request(pull_request)
            if not tokens.intersection({"--comment", "-c"}):
                return True
        if re.match(r"^api(?:\s|$)", normalized) and _blocked_api_operation(arguments[3:]):
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
            if _is_develop_pull_request(tool_input):
                return None
            return _deny("AIはdevelop以外のPRへ正式なレビュー判断を送信しません。")
        return _deny("未知のレビュー種別は許可しません。COMMENTとして助言してください。")

    if operation == MERGE_OPERATION:
        if _is_develop_pull_request(tool_input):
            return None
        return _deny("AIはdevelop以外のPRをmergeしません。")

    if operation in BLOCKED_OPERATIONS:
        return _deny(
            "AIはレビュー却下、会話解決、auto-mergeを実行しません。対象PRを人間へ引き渡してください。"
        )

    if tool_name not in {"Bash", "shell_command"}:
        return None
    command = _command_from(tool_input)
    if command is None:
        return _deny("shell commandを確認できないため、PRガバナンスhookが実行を拒否します。")
    if _blocked_shell_operation(command):
        return _deny("AIはgh経由でdevelop以外の正式なレビュー判断またはmergeを実行しません。")
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
