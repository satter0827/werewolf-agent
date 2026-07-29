"""Setup catalog、preview、永続化を扱うapplication facadeを定義する."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from werewolf_agent.application.constants import DeliberationLevel
from werewolf_agent.application.errors import (
    AppError,
    ConfigError,
    ErrorCode,
    ResourceNotFoundError,
)
from werewolf_agent.application.facade import Actor, _public_result
from werewolf_agent.application.messages import message_player_count_between
from werewolf_agent.application.models import (
    CreateGameCommand,
    GameApplicationConfig,
    GameSetupOptionsResult,
    PlayerPreviewResult,
    SetupValidationResult,
)
from werewolf_agent.application.ports import SetupRepository
from werewolf_agent.application.replay import checksum_payload
from werewolf_agent.application.setup_catalog import SetupTemplateCatalog
from werewolf_agent.application.setup_document import GameSetupDocument
from werewolf_agent.application.setup_options import (
    prepare_create_command,
    preview_players,
    setup_catalog_options,
    validate_setup_document,
)
from werewolf_agent.application.setup_records import SavedSetupRevision, SavedSetupSummary
from werewolf_agent.application.validation import non_blank


class SetupApplication:
    """再利用可能なゲームsetupの認可と調整を所有する."""

    def __init__(
        self,
        catalog: SetupTemplateCatalog,
        config: GameApplicationConfig,
        repository: SetupRepository | None = None,
    ) -> None:
        """Setup catalog、repository、検証上限を結び付ける."""
        self._catalog = catalog
        self._config = config
        self._repository = repository

    def catalog(self) -> GameSetupOptionsResult:
        """Template metadataとeditor上限を返す."""
        return setup_catalog_options(self._config, self._catalog)

    def template(self, template_id: str) -> GameSetupDocument:
        """同梱する一つの完全setup文書を返す."""
        try:
            return self._catalog.require_document(template_id)
        except KeyError as exc:
            raise ResourceNotFoundError("指定したゲーム設定が見つかりません。") from exc

    def preview(self, document: GameSetupDocument, *, seed: int | None) -> PlayerPreviewResult:
        """決定的で公開可能なplayer previewを返す."""
        self._validate_player_count(document)
        return preview_players(document, seed=seed)

    def validate(self, payload: Mapping[str, object]) -> SetupValidationResult:
        """完全な文書をschemaとruntime上限に対して検証する."""
        result = validate_setup_document(payload)
        self._validate_count(result.player_count)
        return result

    def prepare_create(
        self,
        document: GameSetupDocument,
        *,
        seed: int | None,
        manual_player_id: str | None,
        llm_mode: Literal["fake", "paid"],
        deliberation_level: DeliberationLevel,
    ) -> CreateGameCommand:
        """Queue送信前に完全でimmutableなcommandを解決する."""
        self._validate_player_count(document)
        return prepare_create_command(
            document,
            seed=seed,
            manual_player_id=manual_player_id,
            llm_mode=llm_mode,
            deliberation_level=deliberation_level,
        )

    def create(
        self,
        actor: Actor,
        *,
        display_name: str,
        document: GameSetupDocument,
    ) -> SavedSetupRevision:
        """ログイン済みownerの最初のimmutable revisionを保存する."""
        self._require_member(actor)
        self._validate_player_count(document)
        setup_checksum, mechanics_checksum = _checksums(document)
        repository = self._require_repository()
        return _public_result(
            lambda: repository.create(
                owner_user_id=actor.user_id,
                display_name=non_blank(display_name, "display_name"),
                document=document,
                setup_checksum=setup_checksum,
                mechanics_checksum=mechanics_checksum,
            )
        )

    def list_setups(self, actor: Actor) -> list[SavedSetupSummary]:
        """ログイン済みactorが所有するsetup概要を返す."""
        self._require_member(actor)
        return _public_result(
            lambda: self._require_repository().list_setups(owner_user_id=actor.user_id)
        )

    def get(
        self,
        actor: Actor,
        setup_id: str,
        *,
        revision: int | None = None,
    ) -> SavedSetupRevision:
        """他者の存在を開示せず、所有するsetup revisionを返す."""
        self._require_member(actor)
        result = _public_result(
            lambda: self._require_repository().get(
                setup_id,
                owner_user_id=actor.user_id,
                revision=revision,
            )
        )
        if result is None:
            raise ResourceNotFoundError("指定したゲーム設定が見つかりません。")
        return result

    def revisions(self, actor: Actor, setup_id: str) -> list[SavedSetupRevision]:
        """所有するsetupのimmutableなrevision履歴を返す."""
        self.get(actor, setup_id)
        return _public_result(
            lambda: self._require_repository().list_revisions(setup_id, owner_user_id=actor.user_id)
        )

    def save_revision(
        self,
        actor: Actor,
        setup_id: str,
        *,
        expected_revision: int,
        document: GameSetupDocument,
    ) -> SavedSetupRevision:
        """呼出元が期待するrevisionが最新の場合にrevisionを追加する."""
        self._require_member(actor)
        self._validate_player_count(document)
        setup_checksum, mechanics_checksum = _checksums(document)
        return _public_result(
            lambda: self._require_repository().add_revision(
                setup_id,
                owner_user_id=actor.user_id,
                expected_revision=expected_revision,
                document=document,
                setup_checksum=setup_checksum,
                mechanics_checksum=mechanics_checksum,
            )
        )

    @staticmethod
    def _require_member(actor: Actor) -> None:
        if actor.is_anonymous:
            raise AppError(
                "ゲーム設定を保存するにはログインしてください。",
                code=ErrorCode.AUTHORIZATION_FAILED,
            )

    def _require_repository(self) -> SetupRepository:
        if self._repository is None:
            raise ConfigError("setup repositoryが構成されていません。")
        return self._repository

    def _validate_player_count(self, document: GameSetupDocument) -> None:
        self._validate_count(sum(document.mechanics.role_counts.values()))

    def _validate_count(self, player_count: int) -> None:
        if not self._config.min_players <= player_count <= self._config.max_players:
            raise ConfigError(
                message_player_count_between(self._config.min_players, self._config.max_players)
            )


def _checksums(document: GameSetupDocument) -> tuple[str, str]:
    return (
        checksum_payload(document.model_dump(mode="json")),
        checksum_payload(document.mechanics.model_dump(mode="json")),
    )


__all__ = ["SetupApplication"]
