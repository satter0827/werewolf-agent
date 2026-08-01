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
from werewolf_agent.domain.state import (
    Action,
    DeathReactionResolution,
    DiscussionResolution,
    DiscussionRound,
    GameConfig,
    GameState,
    KnowledgeResolution,
    NightResolution,
    VoteResolution,
    WinResult,
)

if TYPE_CHECKING:
    from werewolf_agent.domain.definitions import RuleSetDefinition

RULE_PACK_CONTRACT_VERSION = "0.7.0"
CORE_RULE_PACK_ID = "core"
CORE_RULE_PACK_IMPLEMENTATION_VERSION = "0.7.0"
CORE_RULE_PACK_FINGERPRINT = sha256(b"werewolf-agent:core-rule-pack:0.7.0").hexdigest()


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
        if len(self.fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in self.fingerprint
        ):
            raise ValueError("fingerprint must be a lowercase SHA-256 digest")

    def to_mapping(self) -> dict[str, str]:
        """永続化と実験provenanceへ使用する正規表現を返す."""
        return {
            "provider_id": self.provider_id,
            "contract_version": self.contract_version,
            "implementation_version": self.implementation_version,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> RulePackManifest:
        """外部表現から検証済みmanifestを構築する."""
        return cls(
            provider_id=_manifest_text(value, "provider_id"),
            contract_version=_manifest_text(value, "contract_version"),
            implementation_version=_manifest_text(value, "implementation_version"),
            fingerprint=_manifest_text(value, "fingerprint"),
        )


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
    ) -> VoteResolution:
        """現在の投票を集計し、一つの検証可能なOutcomeを返す."""
        ...


class AbilityPolicy(Protocol):
    """夜の能力入力からstateを変更せず解決Outcomeを返すpolicy契約."""

    def resolve_night(
        self,
        state: GameState,
        pending_actions: Mapping[str, Action],
        random: random.Random,
    ) -> NightResolution:
        """一夜の能動能力と受動耐性を解決して検証可能なOutcomeを返す."""
        ...

    def resolve_death_reactions(
        self,
        state: GameState,
        newly_dead_player_ids: tuple[str, ...],
        random: random.Random,
    ) -> DeathReactionResolution:
        """新たな死亡から連鎖する能力反応を順序付きOutcomeとして返す."""
        ...

    def resolve_knowledge(self, state: GameState) -> KnowledgeResolution:
        """設定済みknowledge能力からobserver非依存の知識候補を返す."""
        ...


class DiscussionPolicy(Protocol):
    """議論入力からstateを変更せずround Outcomeを返すpolicy契約."""

    def start(self, state: GameState) -> DiscussionRound:
        """一日の開始時に最初の議論roundを返す."""
        ...

    def resolve(
        self,
        state: GameState,
        round_: DiscussionRound,
        submissions: Mapping[str, Action],
    ) -> DiscussionResolution:
        """現在roundの提出から公開内容と次roundを返す."""
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
    ability_policy: AbilityPolicy
    voting_policy: VotingPolicy
    discussion_policy: DiscussionPolicy
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

    def compile(
        self,
        provider_id: str,
        definition: RuleSetDefinition,
        *,
        expected_manifest: RulePackManifest | None = None,
    ) -> CompiledRuleSet:
        """登録済みproviderをcompileし、宣言したidentityとの一致を検証する."""
        provider = self.require(provider_id)
        rules = provider.compile(definition)
        if rules.manifest != provider.manifest:
            raise ValueError("compiled rule pack manifest does not match its provider")
        if expected_manifest is not None and rules.manifest != expected_manifest:
            raise ValueError("registered rule pack does not match the persisted manifest")
        return rules


def _manifest_text(value: Mapping[str, object], field_name: str) -> str:
    item = value[field_name]
    if not isinstance(item, str):
        raise ValueError(f"{field_name} must be a string")
    return item


__all__ = [
    "CORE_RULE_PACK_FINGERPRINT",
    "CORE_RULE_PACK_ID",
    "CORE_RULE_PACK_IMPLEMENTATION_VERSION",
    "RULE_PACK_CONTRACT_VERSION",
    "AbilityPolicy",
    "CompiledRuleSet",
    "CoreVictoryPolicy",
    "DiscussionPolicy",
    "RulePackManifest",
    "RulePackProvider",
    "RulePolicyRegistry",
    "VictoryPolicy",
    "VotingPolicy",
]
