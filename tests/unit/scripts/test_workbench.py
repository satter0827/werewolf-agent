"""VS Code workbench commandの安全境界。"""

from pathlib import Path

from scripts.workbench import __main__ as workbench


def test_local_llm_review_delegates_to_agent_preflight(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        workbench,
        "preflight",
        lambda: (
            "passed",
            {
                "configured_model": "local-model",
                "validation_status": "valid",
                "usage": {"input_tokens": 123, "output_tokens": 9},
            },
        ),
    )

    result = workbench._review_local_llm(tmp_path)

    assert result == 0
    transcript = (tmp_path / "preflight.json").read_text(encoding="utf-8")
    assert "local-model" in transcript
    assert '"input_tokens": 123' in transcript


def test_local_llm_review_preserves_blocked_diagnostic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        workbench,
        "preflight",
        lambda: ("blocked", {"message": "slow local model", "error_type": "ReadTimeout"}),
    )

    result = workbench._review_local_llm(tmp_path)

    assert result == 2
    transcript = (tmp_path / "transcript.txt").read_text(encoding="utf-8")
    assert "slow local model" in transcript


def test_local_llm_review_marks_fallback_as_degraded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        workbench,
        "preflight",
        lambda: ("degraded", {"validation_status": "fallback"}),
    )

    result = workbench._review_local_llm(tmp_path)

    assert result == 1
