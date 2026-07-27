"""OpenAI-compatible chat adapter contract without model inference."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from langchain_openai import ChatOpenAI

from werewolf_agent.adapters.llm.model_adapters import (
    LangChainChatDecisionModel,
    LlmModelInvocationError,
)
from werewolf_agent.agents.models import (
    AgentModelDecision,
    AgentObservation,
    DecisionTask,
    DeliberationLevel,
    ModelMessage,
    ModelRequest,
)

BASE_URL = "http://127.0.0.1:18765/v1"
COMPLETIONS_URL = f"{BASE_URL}/chat/completions"


def request() -> ModelRequest:
    context = {"legal": {"actions": ["vote"], "targets": {"vote": ["p2"]}}}
    observation = AgentObservation.model_validate(
        {
            "phase": "voting",
            "day": 1,
            "me": {"id": "p1", "name": "Alice", "status": "alive"},
            "players": [
                {"id": "p1", "name": "Alice", "status": "alive"},
                {"id": "p2", "name": "Bob", "status": "alive"},
            ],
            "available_actions": ["vote"],
            "legal_targets": {"vote": ["p2"]},
        }
    )
    return ModelRequest(
        task=DecisionTask(
            player_id="p1",
            observation=observation,
            deliberation_level=DeliberationLevel.STANDARD,
            output_token_limit=96,
            context=context,
            context_checksum="checksum",
        ),
        messages=(
            ModelMessage(role="system", content="Return JSON."),
            ModelMessage(role="human", content=json.dumps(context)),
        ),
        response_schema=AgentModelDecision.model_json_schema(),
        prompt_checksum="prompt-checksum",
    )


def adapter() -> LangChainChatDecisionModel:
    return LangChainChatDecisionModel(
        model=ChatOpenAI(
            model="stub-model",
            api_key="stub-key",
            base_url=BASE_URL,
            max_retries=0,
            temperature=0,
        ),
        provider_name="lmstudio",
        model_name="stub-model",
        base_url=BASE_URL,
        timeout_seconds=1,
        max_tokens=128,
    )


@respx.mock
def test_openai_compatible_adapter_sends_chat_request_and_normalizes_usage() -> None:
    route = respx.post(COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-stub",
                "object": "chat.completion",
                "created": 1,
                "model": "stub-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": '{"type":"vote","target_id":"p2"}',
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
            },
        )
    )

    response = adapter().invoke(request())

    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "stub-model"
    assert sent["max_completion_tokens"] == 96
    assert [message["role"] for message in sent["messages"]] == ["system", "user"]
    assert response.content == '{"type":"vote","target_id":"p2"}'
    assert response.usage == {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17}
    assert response.finish_reason == "stop"


@respx.mock
def test_openai_compatible_adapter_converts_transport_error_once() -> None:
    route = respx.post(COMPLETIONS_URL).mock(return_value=httpx.Response(503))

    with pytest.raises(LlmModelInvocationError) as raised:
        adapter().invoke(request())

    assert len(route.calls) == 1
    assert raised.value.context["llm_provider"] == "lmstudio"
    assert raised.value.context["llm_model"] == "stub-model"
