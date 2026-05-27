"""Agent factory wiring for interface applications."""

from __future__ import annotations

from werewolf_agent.interface.application.settings import build_fake_llm_config
from werewolf_agent.interface.shared.settings import AppSettings
from werewolf_agent.usecase.jobs import AgentFactory, FakeLlmAgentFactory


def build_agent_factory(settings: AppSettings) -> AgentFactory:
    """Return the configured automated-player factory."""
    return FakeLlmAgentFactory(config=build_fake_llm_config(settings))
