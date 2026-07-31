"""Pythonプロセスへapplicationを直接組み込むcomposition boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, overload
from uuid import UUID

from werewolf_agent.application.actor import Actor
from werewolf_agent.application.constants import MANUAL_AGENT_TYPE
from werewolf_agent.application.errors import ConfigError
from werewolf_agent.application.facade import GameApplication
from werewolf_agent.application.memory import InMemoryGameRepository, InMemorySetupRepository
from werewolf_agent.application.models import (
    AdvanceGameCommand,
    AdvanceGameResult,
    ApplicationContext,
    CreateGameCommand,
    GameApplicationConfig,
    GameResult,
    PlayerActionCommand,
    PlayerActionResult,
    StoredGame,
)
from werewolf_agent.application.operations import AccessPolicy
from werewolf_agent.application.ports import GameRepository, SetupRepository
from werewolf_agent.application.setup_catalog import SetupTemplateCatalog
from werewolf_agent.application.setup_facade import SetupApplication
from werewolf_agent.domain import RulePolicyRegistry


class SingleTenantAccessPolicy(AccessPolicy):
    """一つの信頼済み利用者だけへgameとmanual seatを公開するpolicy."""

    def __init__(self, *, user_id: str, repository: GameRepository) -> None:
        """Tenant主体と同じ状態repositoryへpolicyを固定する."""
        self._user_id = user_id
        self._repository = repository

    def require_game_access(self, game_id: str, *, user_id: str) -> None:
        """Tenant主体が所有する既存gameへのaccessを要求する."""
        if user_id != self._user_id or self._game(game_id) is None:
            raise PermissionError("game access denied")

    def require_player_access(self, game_id: str, player_id: str, *, user_id: str) -> None:
        """Tenant主体に設定されたmanual seatへのaccessを要求する."""
        if user_id != self._user_id:
            raise PermissionError("player access denied")
        game = self._game(game_id)
        if game is None:
            raise PermissionError("player access denied")
        agent_types = game.config.get("player_agent_types")
        if not isinstance(agent_types, Mapping) or agent_types.get(player_id) != MANUAL_AGENT_TYPE:
            raise PermissionError("player access denied")

    def _game(self, game_id: str) -> StoredGame | None:
        try:
            parsed = UUID(game_id)
        except ValueError:
            return None
        return self._repository.get(parsed)


class InlineCommandExecutor:
    """Queueを介さずapplication commandを呼出thread内で完了させる."""

    def __init__(self, application: GameApplication, actor: Actor) -> None:
        """実行対象facadeと固定actorを受け取る."""
        self._application = application
        self._actor = actor

    @overload
    def execute(self, command: CreateGameCommand) -> GameResult: ...

    @overload
    def execute(self, command: PlayerActionCommand) -> PlayerActionResult: ...

    @overload
    def execute(self, command: AdvanceGameCommand) -> AdvanceGameResult: ...

    def execute(
        self,
        command: CreateGameCommand | PlayerActionCommand | AdvanceGameCommand,
    ) -> GameResult | PlayerActionResult | AdvanceGameResult:
        """型付きcommandを同期実行し、対応するapplication resultを返す."""
        if isinstance(command, CreateGameCommand):
            return self._application.create(command)
        if isinstance(command, PlayerActionCommand):
            return self._application.submit_action(self._actor, command)
        if command.expected_version is None:
            raise ConfigError("inline advanceにはexpected_versionが必要です。")
        return self._application.advance(
            str(command.game_id),
            self._actor,
            command.expected_version,
        )


@dataclass(frozen=True)
class EmbeddedApplication:
    """外部serviceなしで利用するapplication facade一式."""

    actor: Actor
    games: GameApplication
    setups: SetupApplication
    commands: InlineCommandExecutor


def create_embedded_application(
    *,
    user_id: str,
    config: GameApplicationConfig,
    setup_catalog: SetupTemplateCatalog,
    game_repository: GameRepository | None = None,
    setup_repository: SetupRepository | None = None,
    access_policy: AccessPolicy | None = None,
    allow_reveal: bool = False,
    create_llm_mode: Literal["fake", "paid"] = "fake",
    rule_packs: RulePolicyRegistry | None = None,
) -> EmbeddedApplication:
    """明示した依存だけからsingle-tenant applicationを構築する."""
    if not isinstance(allow_reveal, bool):
        raise ConfigError("allow_revealはbooleanで指定してください。")
    if create_llm_mode not in {"fake", "paid"}:
        raise ConfigError("create_llm_modeはfakeまたはpaidで指定してください。")
    actor = Actor(user_id=user_id, is_admin=allow_reveal)
    if game_repository is not None and access_policy is None:
        raise ConfigError("外部game repositoryにはaccess_policyが必要です。")
    games_store = (
        game_repository
        if game_repository is not None
        else InMemoryGameRepository(owner_user_id=actor.user_id)
    )
    setups_store = setup_repository if setup_repository is not None else InMemorySetupRepository()
    if rule_packs is None:
        context = ApplicationContext(
            repository=games_store,
            config=config,
            create_llm_mode=create_llm_mode,
        )
    else:
        context = ApplicationContext(
            repository=games_store,
            config=config,
            create_llm_mode=create_llm_mode,
            rule_packs=rule_packs,
        )
    games = GameApplication(
        context,
        access_policy=(
            access_policy
            if access_policy is not None
            else SingleTenantAccessPolicy(
                user_id=actor.user_id,
                repository=games_store,
            )
        ),
    )
    return EmbeddedApplication(
        actor=actor,
        games=games,
        setups=SetupApplication(setup_catalog, config, setups_store),
        commands=InlineCommandExecutor(games, actor),
    )


__all__ = [
    "EmbeddedApplication",
    "InlineCommandExecutor",
    "SingleTenantAccessPolicy",
    "create_embedded_application",
]
