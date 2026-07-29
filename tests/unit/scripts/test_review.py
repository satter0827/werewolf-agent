"""レビュー証拠commandの安全境界。"""

from pathlib import Path

from scripts.review import __main__ as review


def test_local_llm_review_delegates_to_agent_preflight(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        review,
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
    assert review._review_local_llm(tmp_path) == 0
    transcript = (tmp_path / "preflight.json").read_text(encoding="utf-8")
    assert "local-model" in transcript
    assert '"input_tokens": 123' in transcript


def test_local_llm_review_preserves_blocked_diagnostic(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        review,
        "preflight",
        lambda: ("blocked", {"message": "slow local model", "error_type": "ReadTimeout"}),
    )
    assert review._review_local_llm(tmp_path) == 2
    assert "slow local model" in (tmp_path / "transcript.txt").read_text(encoding="utf-8")


def test_local_llm_review_marks_fallback_as_degraded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        review,
        "preflight",
        lambda: ("degraded", {"validation_status": "fallback"}),
    )
    assert review._review_local_llm(tmp_path) == 1
