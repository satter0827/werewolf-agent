"""Notebook専用Fakeゲームデモの安全性と決定性を検査する。"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest
from notebooks.werewolf_demo import DemoLimits, FakeGameDemo

from werewolf_agent.domain import Action, RuleViolation

ROOT = Path(__file__).resolve().parents[3]


def test_root_import_exposes_only_version_without_loading_product_layers() -> None:
    """root importでversion以外の公開面と製品layerを初期化しない。"""
    script = """
import json
import sys
import werewolf_agent

assert not hasattr(werewolf_agent, "Game")
for prefix in (
    "werewolf_agent.domain",
    "werewolf_agent.application",
    "werewolf_agent.adapters",
    "werewolf_agent.settings",
    "werewolf_agent.agents",
):
    assert not any(name == prefix or name.startswith(prefix + ".") for name in sys.modules)
print(json.dumps(sorted(werewolf_agent.__all__)))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["__version__"]


def test_fake_demo_steps_once_and_completes_deterministically() -> None:
    """FakeListChatModel経路で一操作と完走結果を再現する。"""
    demo = FakeGameDemo.create(seed=7)

    first_step = demo.step()
    assert first_step is not None
    assert first_step.operation == "action"
    assert first_step.private_actor_omitted
    assert not first_step.private_target_omitted
    assert first_step.actor_id is None
    assert first_step.action_type == "pass"
    assert first_step.decision is not None
    assert first_step.decision.validation_status == "valid"

    result = demo.run()
    repeated = FakeGameDemo.create(seed=7).run()

    assert result.completed
    assert result.stop_reason == "finished"
    assert result.winner_id in {"village", "werewolf", "fox"}
    assert result.checksum == repeated.checksum
    assert result.action_count == repeated.action_count
    assert all(not decision.provider_error for decision in result.decisions)


def test_fake_demo_distinguishes_private_actor_and_target_omission() -> None:
    """private actorと、実際に存在するprivate targetだけを省略表示する。"""
    demo = FakeGameDemo.create(seed=7)
    private_pass = None
    private_targeted_action = None
    while private_pass is None or private_targeted_action is None:
        step = demo.step()
        assert step is not None
        if step.action_type == "pass":
            private_pass = step
        if step.action_type == "use_ability" and step.private_target_omitted:
            private_targeted_action = step

    assert private_pass.private_actor_omitted
    assert not private_pass.private_target_omitted
    assert private_pass.actor_id is None
    assert private_targeted_action.private_actor_omitted
    assert private_targeted_action.private_target_omitted
    assert private_targeted_action.actor_id is None


def test_fake_demo_distinguishes_seeds_and_reports_limits() -> None:
    """seed namespaceと実行上限を安全な終了理由として返す。"""
    first = FakeGameDemo.create(seed=7).run()
    second = FakeGameDemo.create(seed=8).run()
    action_limited = FakeGameDemo.create(
        seed=7,
        limits=DemoLimits(max_actions=1),
    ).run()
    phase_limited = FakeGameDemo.create(
        seed=7,
        limits=DemoLimits(max_phases=1),
    ).run()

    assert first.checksum != second.checksum
    assert not action_limited.completed
    assert action_limited.stop_reason == "max_actions"
    assert action_limited.action_count == 1
    assert not phase_limited.completed
    assert phase_limited.stop_reason == "max_phases"
    assert phase_limited.phase_count == 1


def test_demo_preserves_failed_action_atomicity_and_restores_snapshot() -> None:
    """失敗した操作が状態を変えず、snapshotを同じ規則で復元できる。"""
    demo = FakeGameDemo.create(seed=7)
    before = demo.game.snapshot()

    with pytest.raises(RuleViolation):
        demo.game.submit(Action.vote("unknown-player", "unknown-target"))

    assert demo.game.snapshot() == before
    restored = demo.game.restore(before, rules=demo.rules)
    assert restored.snapshot() == before


def test_demo_results_do_not_retain_private_llm_payloads() -> None:
    """Notebook向けresultからprompt、response、対象、役職を排除する。"""
    result = FakeGameDemo.create(seed=7).run()
    document = json.dumps(asdict(result), ensure_ascii=False, default=str)

    for forbidden in (
        "prompt_messages",
        "raw_response",
        "parsed_decision",
        "request_payload",
        "target_id",
        "role_id",
    ):
        assert forbidden not in document


def test_demo_limits_require_positive_values() -> None:
    """停止不能な上限設定を拒否する。"""
    with pytest.raises(ValueError):
        DemoLimits(max_phases=0)
    with pytest.raises(ValueError):
        DemoLimits(max_actions=0)


def test_demo_accepts_public_deliberation_level_values() -> None:
    """内部enumをimportせず公開文字列で熟考レベルを変更する。"""
    quick = FakeGameDemo.create(deliberation_level="quick")

    assert quick.step() is not None
    with pytest.raises(ValueError, match="unsupported"):
        FakeGameDemo.create(deliberation_level="unsupported")
