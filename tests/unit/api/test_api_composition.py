"""API composition rootのRule Pack注入契約."""

from collections.abc import Callable

from werewolf_agent.api import bootstrap
from werewolf_agent.application import (
    RulePackRegistry,
    create_core_rule_policy_registry,
)
from werewolf_agent.settings import AppSettings


def test_create_app_forwards_the_injected_rule_pack_registry(
    monkeypatch,
) -> None:
    """APIが利用者のregistryを置換せずrequest dependencyへ固定する."""
    registry = create_core_rule_policy_registry()
    captured: list[RulePackRegistry] = []

    def dependency(
        _settings: AppSettings,
        _runtime: object,
        rule_packs: RulePackRegistry,
    ) -> Callable[[], None]:
        captured.append(rule_packs)
        return lambda: None

    monkeypatch.setattr(bootstrap, "_service_dependency", dependency)

    bootstrap.create_app(AppSettings(_env_file=None), rule_packs=registry)

    assert captured == [registry]
