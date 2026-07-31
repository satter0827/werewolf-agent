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
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


HOOK = _load_hook()
ADD_REVIEW_TOOL = "mcp__codex_apps__github_add_review_to_pr"
MERGE_TOOL = "mcp__codex_apps__github_merge_pull_request"
DEVELOP_STATE = HOOK.PullRequestState(base_ref="develop", head_sha="head-sha")
MAIN_STATE = HOOK.PullRequestState(base_ref="main", head_sha="head-sha")


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


def _assert_denied(result: dict[str, object] | None) -> None:
    assert result is not None
    output = result["hookSpecificOutput"]
    assert isinstance(output, Mapping)
    assert output["hookEventName"] == "PreToolUse"
    assert output["permissionDecision"] == "deny"
    assert output["permissionDecisionReason"]


@pytest.mark.parametrize("state", [DEVELOP_STATE, MAIN_STATE])
def test_comment_review_requires_current_head_on_every_branch(
    state: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """COMMENT reviewもtarget branchの最新headへ固定する。"""
    monkeypatch.setattr(HOOK, "_pull_request_state", lambda _input: state)

    assert (
        HOOK.evaluate(
            {
                "tool_name": ADD_REVIEW_TOOL,
                "tool_input": {
                    "action": "COMMENT",
                    "commit_id": "head-sha",
                    "pr_number": 123,
                },
            }
        )
        is None
    )
    for commit_id in (None, "stale-sha"):
        result = HOOK.evaluate(
            {
                "tool_name": ADD_REVIEW_TOOL,
                "tool_input": {
                    "action": "COMMENT",
                    "commit_id": commit_id,
                    "pr_number": 123,
                },
            }
        )
        _assert_denied(result)


@pytest.mark.parametrize("action", ["APPROVE", "REQUEST_CHANGES", "approve"])
def test_formal_review_is_denied_outside_develop(
    action: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """develop以外の正式レビュー判断を拒否する。"""
    monkeypatch.setattr(HOOK, "_pull_request_state", lambda _input: MAIN_STATE)

    result = HOOK.evaluate(
        {
            "tool_name": ADD_REVIEW_TOOL,
            "tool_input": {"action": action, "commit_id": "head-sha", "pr_number": 123},
        }
    )

    _assert_denied(result)


@pytest.mark.parametrize("action", ["APPROVE", "REQUEST_CHANGES"])
def test_develop_formal_review_requires_current_head(
    action: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """developの正式判断はGitHub上の最新headへ固定する。"""
    monkeypatch.setattr(HOOK, "_pull_request_state", lambda _input: DEVELOP_STATE)

    assert (
        HOOK.evaluate(
            {
                "tool_name": ADD_REVIEW_TOOL,
                "tool_input": {
                    "action": action,
                    "commit_id": "head-sha",
                    "pr_number": 123,
                },
            }
        )
        is None
    )
    for commit_id in (None, "stale-sha"):
        result = HOOK.evaluate(
            {
                "tool_name": ADD_REVIEW_TOOL,
                "tool_input": {
                    "action": action,
                    "commit_id": commit_id,
                    "pr_number": 123,
                },
            }
        )
        _assert_denied(result)


def test_develop_merge_requires_method_and_current_head(monkeypatch: pytest.MonkeyPatch) -> None:
    """develop mergeはmerge commitと最新head SHAを同時に要求する。"""
    monkeypatch.setattr(HOOK, "_pull_request_state", lambda _input: DEVELOP_STATE)
    valid = {
        "pr_number": 123,
        "merge_method": "merge",
        "expected_head_sha": "head-sha",
    }

    assert HOOK.evaluate({"tool_name": MERGE_TOOL, "tool_input": valid}) is None

    for invalid in (
        valid | {"merge_method": "squash"},
        valid | {"merge_method": "rebase"},
        valid | {"expected_head_sha": "stale-sha"},
        {"pr_number": 123, "merge_method": "merge"},
    ):
        _assert_denied(HOOK.evaluate({"tool_name": MERGE_TOOL, "tool_input": invalid}))


def test_merge_is_denied_outside_develop(monkeypatch: pytest.MonkeyPatch) -> None:
    """mainを含むdevelop以外のmergeを拒否する。"""
    monkeypatch.setattr(HOOK, "_pull_request_state", lambda _input: MAIN_STATE)

    result = HOOK.evaluate(
        {
            "tool_name": MERGE_TOOL,
            "tool_input": {
                "pr_number": 123,
                "merge_method": "merge",
                "expected_head_sha": "head-sha",
            },
        }
    )

    _assert_denied(result)


@pytest.mark.parametrize("operation", sorted(HOOK.BLOCKED_OPERATIONS))
def test_review_state_mutations_are_denied(operation: str) -> None:
    """人間が所有するレビュー状態の変更を拒否する。"""
    result = HOOK.evaluate(
        {
            "tool_name": f"mcp__codex_apps__github_{operation}",
            "tool_input": {"pull_number": 123},
        }
    )

    _assert_denied(result)


@pytest.mark.parametrize(
    ("tool_name", "tool_input"),
    [
        ("mcp__codex_apps__github_create_pull_request", {"title": "change"}),
        ("mcp__codex_apps__github_add_comment_to_issue", {"comment": "advice"}),
        ("mcp__codex_apps__github_reply_to_review_comment", {"comment": "reply"}),
        ("mcp__codex_apps__github_fetch_pr", {"pr_number": 123}),
    ],
)
def test_non_judgment_github_operations_are_allowed(
    tool_name: str,
    tool_input: Mapping[str, Any],
) -> None:
    """PR作成、参照、通常コメントを維持する。"""
    assert HOOK.evaluate({"tool_name": tool_name, "tool_input": tool_input}) is None


def test_pull_request_state_is_resolved_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """baseとheadは呼出入力で自己申告させずGitHubから取得する。"""
    commands: list[list[str]] = []

    def completed(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        output = json.dumps({"baseRefName": "develop", "headRefOid": "head-sha"})
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(HOOK.subprocess, "run", completed)

    state = HOOK._pull_request_state({"pr_number": 123, "repository_full_name": "example/repo"})

    assert state == DEVELOP_STATE
    assert commands == [
        [
            "gh",
            "pr",
            "view",
            "123",
            "--json",
            "baseRefName,headRefOid",
            "--repo",
            "example/repo",
        ]
    ]


@pytest.mark.parametrize(
    "tool_input",
    [
        {"pr_number": 123},
        {"pr_number": True, "repository_full_name": "example/repo"},
        {"repository_full_name": "example/repo"},
    ],
)
def test_pull_request_state_requires_explicit_repository_and_number(
    tool_input: Mapping[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """現在repoや真偽値へ曖昧にfallbackしない。"""
    monkeypatch.setattr(
        HOOK.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("invalid input must not query GitHub"),
    )

    assert HOOK._pull_request_state(tool_input) is None


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.CompletedProcess(["gh"], 1, "", "not found"),
        subprocess.CompletedProcess(["gh"], 0, "{", ""),
        subprocess.TimeoutExpired(["gh"], 5),
    ],
)
def test_pull_request_state_resolution_fails_closed(
    failure: subprocess.CompletedProcess[str] | subprocess.TimeoutExpired,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub照会失敗時は判断操作を許可しない。"""

    def fail(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if isinstance(failure, subprocess.TimeoutExpired):
            raise failure
        return failure

    monkeypatch.setattr(HOOK.subprocess, "run", fail)

    tool_input = {"pr_number": 123, "repository_full_name": "example/repo"}
    assert HOOK._pull_request_state(tool_input) is None
    _assert_denied(
        HOOK.evaluate(
            {
                "tool_name": MERGE_TOOL,
                "tool_input": {
                    "pr_number": 123,
                    "repository_full_name": "example/repo",
                    "merge_method": "merge",
                    "expected_head_sha": "head-sha",
                },
            }
        )
    )


@pytest.mark.parametrize("tool_input", [{}, {"action": "UNKNOWN"}])
def test_unknown_review_action_fails_closed(tool_input: Mapping[str, Any]) -> None:
    """tool仕様の追加を暗黙に許可しない。"""
    result = _run_hook(ADD_REVIEW_TOOL, tool_input)

    assert result.returncode == 0
    _assert_denied(json.loads(result.stdout))


def test_malformed_json_fails_closed() -> None:
    """解析できないhook入力を許可しない。"""
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input="{",
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0
    _assert_denied(json.loads(result.stdout))


def test_evaluation_error_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """判定処理の例外を有効なdeny応答へ変換する。"""
    stdin = io.StringIO(json.dumps({"tool_name": MERGE_TOOL, "tool_input": {}}))
    stdout = io.StringIO()

    def fail(_: Mapping[str, object]) -> None:
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(HOOK.sys, "stdin", stdin)
    monkeypatch.setattr(HOOK.sys, "stdout", stdout)
    monkeypatch.setattr(HOOK, "evaluate", fail)

    assert HOOK.main() == 0
    _assert_denied(json.loads(stdout.getvalue()))


def test_hook_registration_targets_only_structured_github_tools() -> None:
    """shellを解析せず構造化GitHub toolだけを対象にする。"""
    document = json.loads(HOOK_CONFIG_PATH.read_text(encoding="utf-8"))
    registrations = document["hooks"]["PreToolUse"]

    assert len(registrations) == 1
    matcher = registrations[0]["matcher"]
    assert re.fullmatch(matcher, ADD_REVIEW_TOOL)
    assert re.fullmatch(matcher, MERGE_TOOL)
    assert re.fullmatch(matcher, "Bash") is None
    assert re.fullmatch(matcher, "shell_command") is None
    command_hook = registrations[0]["hooks"][0]
    assert command_hook["type"] == "command"
    assert ".codex/hooks/github_pr_governance.py" in command_hook["command"]
    assert ".codex/hooks/github_pr_governance.py" in command_hook["commandWindows"]


def test_governance_boundary_is_documented_consistently() -> None:
    """AIと人間の責務境界を運用入口へ記載する。"""
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    scripts = (ROOT / "scripts/README.md").read_text(encoding="utf-8")
    template = (ROOT / ".github/PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")

    for document in (agents, scripts):
        assert "inline `COMMENT`" in document
        assert "最新head SHA" in document
        assert "`develop`向けPR" in document
        assert "`main`向けPR" in document
        assert "人間" in document
        assert "merge" in document
    assert "required_approving_review_count`を0" in scripts
    assert "GitHub側の権限制御ではない" in scripts
    assert "shellコマンドを解析しない" in scripts
    assert "develop向けはAIが最新headへの判断を記録" in template
    assert "main向けの正式承認とmergeは人間" in template
