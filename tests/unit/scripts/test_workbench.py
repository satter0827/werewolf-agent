"""VS Code workbench commandの安全境界。"""

from pathlib import Path

import httpx
import respx
from scripts.workbench import __main__ as workbench


def test_local_llm_review_rejects_non_loopback_endpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WEREWOLF_LOCAL_LLM_BASE_URL", "https://paid.example/v1")
    monkeypatch.setenv("WEREWOLF_LOCAL_LLM_MODEL", "model")

    result = workbench._review_local_llm(tmp_path)

    assert result == 2
    assert (tmp_path / "transcript.txt").is_file()
    assert "loopback" in (tmp_path / "transcript.txt").read_text(encoding="utf-8")


@respx.mock
def test_local_llm_review_saves_loopback_conversation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WEREWOLF_LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("WEREWOLF_LOCAL_LLM_MODEL", "local-model")
    route = respx.post("http://127.0.0.1:1234/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"type":"speech","message":"様子を見ます"}',
                        }
                    }
                ]
            },
        )
    )

    result = workbench._review_local_llm(tmp_path)

    assert result == 0
    assert route.called
    conversation = (tmp_path / "conversation.json").read_text(encoding="utf-8")
    assert "様子を見ます" in conversation
    assert "local-model" in conversation


@respx.mock
def test_local_llm_review_preserves_timeout_diagnostic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WEREWOLF_LOCAL_LLM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("WEREWOLF_LOCAL_LLM_MODEL", "local-model")
    respx.post("http://localhost:1234/v1/chat/completions").mock(
        side_effect=httpx.ReadTimeout("slow local model")
    )

    result = workbench._review_local_llm(tmp_path)

    assert result == 2
    transcript = (tmp_path / "transcript.txt").read_text(encoding="utf-8")
    assert "取得できませんでした" in transcript
    assert "slow local model" in transcript


@respx.mock
def test_local_llm_review_preserves_invalid_json_diagnostic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WEREWOLF_LOCAL_LLM_BASE_URL", "http://[::1]:1234/v1")
    monkeypatch.setenv("WEREWOLF_LOCAL_LLM_MODEL", "local-model")
    respx.post("http://[::1]:1234/v1/chat/completions").mock(
        return_value=httpx.Response(200, text="not-json")
    )

    result = workbench._review_local_llm(tmp_path)

    assert result == 2
    transcript = (tmp_path / "transcript.txt").read_text(encoding="utf-8")
    assert "取得できませんでした" in transcript
