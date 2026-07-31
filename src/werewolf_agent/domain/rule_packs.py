"""明示登録するRule Packとstate非変更policyの公開契約を定義する."""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol

from werewolf_agent.domain._model import non_blank
from werewolf_agent.domain.rules.player_rules import check_win
from werewolf_agent.domain.state import Action, GameConfig, GameState, VoteResult, WinResult

if TYPE_CHECKING:
    from werewolf_agent.domain.definitions import RuleSetDefinition

RULE_PACK_CONTRACT_VERSION = "0.2.0"
CORE_RULE_PACK_ID = "core"
CORE_RULE_PACK_IMPLEMENTATION_VERSION = "0.2.0"
CORE_RULE_PACK_FINGERPRINT = sha256(b"werewolf-agent:core-rule-pack:0.2.0").hexdigest()


@dataclass(frozen=True)
class RulePackManifest:
    """一つのRule Pack実装を識別するversion付きmanifestを表す."""

    provider_id: str
    contract_version: str
    implementation_version: str
    fingerprint: str

    def __post_init__(self) -> None:
        """識別子とversionとfingerprintを正規化する."""
        for field_name in (
            "provider_id",
            "contract_version",
            "implementation_version",
            "fingerprint",
        ):
            object.__setattr__(
                self,
                field_name,
                non_blank(getattr(self, field_name), field_name),
            )
        if self.contract_version != RULE_PACK_CONTRACT_VERSION:
            raise ValueError(f"contract_version must be {RULE_PACK_CONTRACT_VERSION}")


class VictoryPolicy(Protocol):
    """Immutable stateから勝敗Outcomeだけを返すpolicy契約."""

    def evaluate(self, state: GameState) -> WinResult | None:
        """勝敗が成立した場合だけ検証可能なOutcomeを返す."""
        ...


class VotingPolicy(Protocol):
    """投票入力からstateを変更せず解決Outcomeを返すpolicy契約."""

    def resolve(
        self,
        state: GameState,
        pending_votes: Mapping[str, Action],
        random: random.Random,
        *,
        vote_round: int,
    ) -> VoteResult:
        """現在の投票を集計し、一つの検証可能なOutcomeを返す."""
        ...


class RulePackProvider(Protocol):
    """Rule Definitionを実行可能なRule Packへcompileする契約."""

    @property
    def manifest(self) -> RulePackManifest:
        """Providerを識別するimmutable manifestを返す."""
        ...

    def compile(self, definition: RuleSetDefinition) -> CompiledRuleSet:
        """検証済みdefinitionを実行可能なrulesetへ変換する."""
        ...


@dataclass(frozen=True)
class CompiledRuleSet:
    """Gameへ注入する設定とstate非変更policyの集合を表す."""

    config: GameConfig
    manifest: RulePackManifest
    voting_policy: VotingPolicy
    victory_policy: VictoryPolicy


class CoreVictoryPolicy:
    """組み込みの村人、人狼、狐の勝敗判定を実装する."""

    def evaluate(self, state: GameState) -> WinResult | None:
        """現在の組み込み勝敗条件を評価する."""
        return check_win(state)


class RulePolicyRegistry:
    """利用者が明示登録したRule Pack Providerだけを保持する."""

    def __init__(self, providers: tuple[RulePackProvider, ...] = ()) -> None:
        """重複しないprovider IDでregistryを構築する."""
        registered: dict[str, RulePackProvider] = {}
        for provider in providers:
            provider_id = provider.manifest.provider_id
            if provider_id in registered:
                raise ValueError(f"duplicate rule pack provider: {provider_id}")
            registered[provider_id] = provider
        self._providers: Mapping[str, RulePackProvider] = MappingProxyType(registered)

    @property
    def provider_ids(self) -> tuple[str, ...]:
        """登録順に安定したprovider IDを返す."""
        return tuple(self._providers)

    def require(self, provider_id: str) -> RulePackProvider:
        """登録済みproviderを返し、未知のIDを拒否する."""
        normalized = non_blank(provider_id, "provider_id")
        try:
            return self._providers[normalized]
        except KeyError as exc:
            raise ValueError(f"unknown rule pack provider: {normalized}") from exc


__all__ = [
    "CORE_RULE_PACK_FINGERPRINT",
    "CORE_RULE_PACK_ID",
    "CORE_RULE_PACK_IMPLEMENTATION_VERSION",
    "RULE_PACK_CONTRACT_VERSION",
    "CompiledRuleSet",
    "CoreVictoryPolicy",
    "RulePackManifest",
    "RulePackProvider",
    "RulePolicyRegistry",
    "VictoryPolicy",
    "VotingPolicy",
]
