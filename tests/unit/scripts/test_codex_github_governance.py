"""CodexのGitHub PR判断操作ガードを検査する。"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
HOOK_PATH = ROOT / ".codex/hooks/github_pr_governance.py"
HOOK_CONFIG_PATH = ROOT / ".codex/hooks.json"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("github_pr_governance", HOOK_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("Codex hookを読み込めません")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HOOK = _load_hook()
ADD_REVIEW_TOOL = "mcp__codex_apps__github_add_review_to_pr"


def _run_hook(tool_name: str, tool_input: Mapping[str, Any]) -> subprocess.CompletedProcess[str]:
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _run_raw_hook(payload: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _assert_denied(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0
    output = json.loads(result.stdout)
    decision = output["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"
    assert decision["permissionDecisionReason"]


@pytest.mark.parametrize("action", ["APPROVE", "REQUEST_CHANGES", "approve"])
def test_formal_review_decisions_are_denied(action: str) -> None:
    """正式なレビュー判断は大文字小文字にかかわらず拒否する。"""
    result = _run_hook(ADD_REVIEW_TOOL, {"action": action, "pull_number": 123})

    _assert_denied(result)


@pytest.mark.parametrize("operation", sorted(HOOK.BLOCKED_OPERATIONS))
@pytest.mark.parametrize("server", ["codex_apps", "renamed_github_connector"])
def test_direct_governance_tools_are_denied(operation: str, server: str) -> None:
    """判断状態を変更するGitHub toolを直接拒否する。"""
    tool_name = f"mcp__{server}__github_{operation}"
    result = _run_hook(tool_name, {"owner": "example", "repo": "repo", "pull_number": 123})

    _assert_denied(result)


@pytest.mark.parametrize(
    ("tool_name", "tool_input"),
    [
        (ADD_REVIEW_TOOL, {"action": "COMMENT"}),
        ("mcp__codex_apps__github_create_pull_request", {"title": "change"}),
        ("mcp__codex_apps__github_add_comment_to_issue", {"body": "advice"}),
        ("mcp__codex_apps__github_reply_to_pull_request_comment", {"body": "reply"}),
        ("mcp__codex_apps__github_request_pull_request_review", {"reviewers": ["human"]}),
        ("mcp__codex_apps__github_get_pull_request", {"pull_number": 123}),
    ],
)
def test_advice_and_pr_work_are_allowed(tool_name: str, tool_input: Mapping[str, Any]) -> None:
    """PR作業と助言コメントは維持する。"""
    result = _run_hook(tool_name, tool_input)

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_review_action_is_independent_of_mcp_server_namespace() -> None:
    """GitHub connectorのserver名が変わってもreview actionを判定する。"""
    result = _run_hook(
        "mcp__renamed_connector__github_add_review_to_pr",
        {"action": "APPROVE", "pull_number": 123},
    )

    _assert_denied(result)


@pytest.mark.parametrize(
    "command",
    [
        "gh pr review 123 --approve",
        "gh pr review 123 --request-changes --body 'fix this'",
        "gh pr review 123 -a",
        "gh pr review 123",
        "gh pr merge 123 --merge",
        "gh -R example/repo pr merge 123 --merge",
        "gh --repo=example/repo pr review 123 --approve",
        "GH_HOST=github.com gh pr merge 123 --merge",
        "env GH_HOST=github.com gh pr review 123 --approve",
        "command gh pr merge 123 --merge",
        "gh.exe pr merge 123 --merge",
        "C:\\tools\\gh.exe pr merge 123 --merge",
        "Write-Output ready; gh pr merge 123 --merge",
        "Write-Output ready && gh pr review 123 --approve",
        'powershell -Command "gh pr review 123 --approve"',
        'powershell -NoProfile -Command "gh pr review 123 --request-changes"',
        'pwsh -Command "gh pr merge 123 --auto"',
        'cmd /c "gh pr merge 123 --merge"',
        'bash -c "gh pr review 123 --approve"',
        "$(gh pr merge 123 --merge)",
        '& "C:\\Program Files\\GitHub CLI\\gh.exe" pr merge 123 --merge',
        "gh api -X POST repos/example/repo/pulls/123/reviews -f event=APPROVE",
        "gh api -XPOST repos/example/repo/pulls/%PR_NUMBER%/reviews -fevent=APPROVE",
        "gh api -X POST repos/example/repo/pulls/123/reviews",
        "gh api --input review.json repos/example/repo/pulls/123/reviews",
        "gh api -X POST repos/example/repo/pulls/123/reviews/456/events",
        "gh api -X POST graphql -f query='mutation { enablePullRequestAutoMerge(input: {}) }'",
        "gh api graphql --input mutation.json",
        "gh api graphql -f query=@mutation.graphql",
        "gh api graphql -f query='mutation { submitPullRequestReview(input: {}) }'",
        "gh api -X POST graphql -f query='mutation { resolveReviewThread(input: {}) }'",
        "gh api -X POST graphql -f query='mutation { unresolveReviewThread(input: {}) }'",
        "gh api -X PUT repos/example/repo/pulls/123/merge",
        "gh api --method=PUT 'repos/example/repo/pulls/$PR_NUMBER/merge'",
        "gh api -X PUT repos/example/repo/pulls/123/reviews/456/dismissals",
    ],
)
def test_shell_equivalents_are_denied(command: str) -> None:
    """PowerShell wrapperとAPI直呼びを含む禁止commandを拒否する。"""
    result = _run_hook("Bash", {"command": command})

    _assert_denied(result)


@pytest.mark.parametrize(
    "command",
    [
        "gh pr view 123",
        "gh pr checks 123",
        "gh pr comment 123 --body 'advice'",
        "gh pr create --title 'change' --body 'details'",
        "gh pr review 123 --comment --body 'advice'",
        "gh api repos/example/repo/pulls/123",
        "gh api repos/example/repo/pulls/123/merge",
        "gh api -X GET repos/example/repo/pulls/123/merge",
        "gh api -X POST repos/example/repo/pulls/123/reviews -f event=COMMENT",
        "gh api -X POST repos/example/repo/pulls/123/reviews/456/events -f event=COMMENT",
        "gh api graphql -f query='query { viewer { login } }'",
        "gh api -X POST repos/example/repo/issues/123/comments -f body=mergePullRequest",
        "gh api -X POST repos/example/repo/issues/123/comments -f body=event=APPROVE",
        'rg -n "gh pr merge" .codex tests',
        'Select-String -Pattern "gh pr review 123 --approve" -Path policy.md',
        'Write-Output "gh pr merge 123"',
        "powershell -Command \"Write-Output 'gh pr merge 123'\"",
    ],
)
def test_read_comment_and_creation_commands_are_allowed(command: str) -> None:
    """参照、作成、通常コメント、COMMENT reviewは許可する。"""
    result = _run_hook("Bash", {"command": command})

    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize("tool_input", [{}, {"action": "UNKNOWN"}])
def test_unknown_review_action_fails_closed(tool_input: Mapping[str, Any]) -> None:
    """tool仕様の追加を暗黙に許可しない。"""
    result = _run_hook(ADD_REVIEW_TOOL, tool_input)

    _assert_denied(result)


def test_malformed_json_fails_closed() -> None:
    """解析できないhook入力を許可しない。"""
    result = _run_raw_hook("{")

    _assert_denied(result)


def test_evaluation_error_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """判定処理の例外を有効なdeny応答へ変換する。"""
    stdin = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": "true"}}))
    stdout = io.StringIO()

    def fail(_: Mapping[str, object]) -> None:
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(HOOK.sys, "stdin", stdin)
    monkeypatch.setattr(HOOK.sys, "stdout", stdout)
    monkeypatch.setattr(HOOK, "evaluate", fail)

    assert HOOK.main() == 0
    decision = json.loads(stdout.getvalue())["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"


def test_hook_registration_covers_every_governance_tool() -> None:
    """hook登録、対象tool、禁止操作一覧を固定する。"""
    document = json.loads(HOOK_CONFIG_PATH.read_text(encoding="utf-8"))
    registrations = document["hooks"]["PreToolUse"]

    assert len(registrations) == 1
    matcher = registrations[0]["matcher"]
    assert re.fullmatch(matcher, "Bash")
    assert re.fullmatch(matcher, ADD_REVIEW_TOOL)
    assert re.fullmatch(matcher, "mcp__renamed_connector__github_merge_pull_request")
    assert re.fullmatch(matcher, "shell_command") is None
    command_hook = registrations[0]["hooks"][0]
    assert command_hook["type"] == "command"
    assert ".codex/hooks/github_pr_governance.py" in command_hook["command"]
    assert ".codex/hooks/github_pr_governance.py" in command_hook["commandWindows"]
    assert {"APPROVE", "REQUEST_CHANGES"} == HOOK.BLOCKED_REVIEW_ACTIONS
    assert {"COMMENT"} == HOOK.ALLOWED_REVIEW_ACTIONS


def test_governance_boundary_is_documented_consistently() -> None:
    """AIと人間の責務境界を運用入口へ記載する。"""
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    scripts = (ROOT / "scripts/README.md").read_text(encoding="utf-8")
    template = (ROOT / ".github/PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")

    for document in (agents, scripts):
        assert "inline `COMMENT`" in document
        assert "人間" in document
        assert "merge" in document
    assert "required_approving_review_count`を0" in scripts
    assert "GitHub側の権限制御ではない" in scripts
    assert "hosted tool" in scripts
    assert "AIのレビューは助言" in template
    assert "人間が未解決会話と必須checkを確認" in template
