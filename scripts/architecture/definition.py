"""Architecture解析と文書生成が共有する唯一の構造定義。"""

from __future__ import annotations

from types import ModuleType

import werewolf_agent.adapters as adapters
import werewolf_agent.agents as agents
import werewolf_agent.contracts as contracts
import werewolf_agent.domain as domain
import werewolf_agent.usecase as usecase

LAYERS = frozenset(
    {
        "adapters",
        "agents",
        "api",
        "configuration",
        "contracts",
        "domain",
        "interfaces",
        "observability",
        "resources",
        "security",
        "usecase",
    }
)

ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    "domain": frozenset({"domain"}),
    "configuration": frozenset({"configuration"}),
    "contracts": frozenset({"configuration", "contracts", "security"}),
    "security": frozenset({"configuration", "contracts", "security"}),
    "observability": frozenset({"configuration", "contracts", "observability", "security"}),
    "agents": frozenset({"agents", "configuration", "contracts"}),
    "usecase": frozenset({"configuration", "contracts", "domain", "usecase"}),
    "adapters": frozenset(
        {
            "adapters",
            "agents",
            "configuration",
            "contracts",
            "domain",
            "observability",
            "security",
            "usecase",
        }
    ),
    "api": frozenset({"api", "configuration", "contracts", "observability", "security", "usecase"}),
    "interfaces": frozenset(
        {
            "adapters",
            "agents",
            "configuration",
            "contracts",
            "interfaces",
            "observability",
            "security",
            "usecase",
        }
    ),
    "resources": frozenset({"resources"}),
}

DEPENDENCY_EXCEPTION_REASONS = {
    ("werewolf_agent.api.bootstrap", "adapters"): (
        "HTTP composition root が adapter 実装を構築する。"
    ),
}
ALLOWED_MODULE_IMPORTS = frozenset(DEPENDENCY_EXCEPTION_REASONS)

PUBLIC_MODULES: tuple[ModuleType, ...] = (domain, usecase, contracts, agents, adapters)

__all__ = [
    "ALLOWED_IMPORTS",
    "ALLOWED_MODULE_IMPORTS",
    "DEPENDENCY_EXCEPTION_REASONS",
    "LAYERS",
    "PUBLIC_MODULES",
]
