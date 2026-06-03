"""Demo game client that never touches backend API or Supabase."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast

from pydantic import BaseModel

import werewolf_agent.usecase.jobs as game_jobs
from werewolf_agent.commons.shared.messages import MESSAGE_GAME_NOT_FOUND
from werewolf_agent.contracts import (
    GameNotFoundError,
    GameStatus,
    InvalidGameIdError,
    ResourceNotFoundError,
)
from werewolf_agent.contracts.schemas import (
    AdvanceGameJobResponse,
    AdvanceGameResponse,
    CreateGameRequest,
    GameListResponse,
    GameResponse,
    GameRevealResponse,
    GameSetupOptionsResponse,
    GameTimelineResponse,
    PlayerActionRequest,
    PlayerActionResponse,
    PlayerObservationResponse,
)
from werewolf_agent.interface.application.settings import (
    build_game_definitions,
    build_game_usecase_config,
    build_llm_definitions,
    build_llm_provider_config,
)
from werewolf_agent.interface.application.telemetry import LoggingTelemetrySink
from werewolf_agent.interface.demo.repository import InMemoryGameRepository
from werewolf_agent.interface.runtime import AppSettings
from werewolf_agent.interface.shared.game_requests import build_create_game_request
from werewolf_agent.interface.shared.setup_options import get_local_setup_options

TModel = TypeVar("TModel", bound=BaseModel)


class DemoGameClient:
    """Use case-backed client for unauthenticated dummy play."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        repository: InMemoryGameRepository | None = None,
    ) -> None:
        """Create a demo client with process-local persistence."""
        self._settings = settings
        self._repository = repository or InMemoryGameRepository()

    def health(self) -> dict[str, str]:
        """Return local demo health."""
        return {"status": "ok", "service": "werewolf-agent-demo"}

    def get_setup_options(self) -> GameSetupOptionsResponse:
        """Return setup options from packaged/configured definitions."""
        return get_local_setup_options(self._settings)

    def create_game(self, request: CreateGameRequest) -> GameResponse:
        """Create one process-local demo game."""
        command = game_jobs.CreateGameCommand(
            seed=request.seed,
            role_counts=request.role_counts,
            manual_player_id=request.manual_player_id,
            rules=request.rules or self._settings.game_definitions.rules.local_rules,
            scenario_id=request.scenario_id,
            setup_preset_id=request.setup_preset_id,
            narration_mode=request.narration_mode or self._settings.game_default_narration_mode,
            character_assignments=request.character_assignments,
            custom_roles=[item for item in request.custom_roles],
            custom_characters=[item for item in request.custom_characters],
        )
        return _wire_model(GameResponse, self._service().create_game(command))

    def get_game(self, game_id: str) -> GameResponse:
        """Return one public demo game state."""
        return _wire_model(
            GameResponse,
            self._not_found_as_resource(
                lambda: self._service().get_game(game_jobs.GetGameQuery(game_id=game_id))
            ),
        )

    def get_game_reveal(self, game_id: str) -> GameRevealResponse:
        """Return full demo reveal information."""
        return _wire_model(
            GameRevealResponse,
            self._not_found_as_resource(
                lambda: self._service().get_game_reveal(
                    game_jobs.GetGameRevealQuery(game_id=game_id)
                )
            ),
        )

    def list_games(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> GameListResponse:
        """Return process-local demo summaries."""
        return _wire_model(
            GameListResponse,
            self._service().list_games(
                game_jobs.ListGamesQuery(
                    status=cast(GameStatus | None, status),
                    limit=limit,
                    offset=offset,
                )
            ),
        )

    def advance_game(self, game_id: str) -> AdvanceGameResponse:
        """Advance one demo game synchronously."""
        return _wire_model(
            AdvanceGameResponse,
            self._not_found_as_resource(
                lambda: self._service().advance_game(game_jobs.AdvanceGameCommand(game_id=game_id))
            ),
        )

    def start_advance_game(self, game_id: str) -> AdvanceGameJobResponse:
        """Run a synchronous demo step and wrap it in the job DTO shape."""
        result = self.advance_game(game_id)
        now = result.state.updated_at or result.state.created_at
        if now is None:
            from datetime import UTC, datetime

            now = datetime.now(UTC)
        return AdvanceGameJobResponse(
            job_id=f"demo-{result.state.version}",
            game_id=result.game_id,
            status="completed",
            state_version=result.state.version,
            result=result,
            created_at=now,
            started_at=now,
            completed_at=now,
            updated_at=now,
        )

    def get_advance_job(self, game_id: str, job_id: str) -> AdvanceGameJobResponse:
        """Demo jobs are synchronous, so return the latest state."""
        _ = job_id
        game = self.get_game(game_id)
        now = game.state.updated_at or game.state.created_at
        if now is None:
            from datetime import UTC, datetime

            now = datetime.now(UTC)
        return AdvanceGameJobResponse(
            job_id=job_id,
            game_id=game_id,
            status="completed",
            state_version=game.state.version,
            created_at=now,
            completed_at=now,
            updated_at=now,
        )

    def get_latest_advance_job(self, game_id: str) -> AdvanceGameJobResponse:
        """Return a completed pseudo-job for the current demo state."""
        return self.get_advance_job(game_id, "demo-latest")

    def get_timeline(
        self,
        game_id: str,
        *,
        after: int = 0,
        limit: int | None = None,
    ) -> GameTimelineResponse:
        """Return demo public timeline items."""
        return _wire_model(
            GameTimelineResponse,
            self._not_found_as_resource(
                lambda: self._service().list_timeline(
                    game_jobs.ListTimelineQuery(game_id=game_id, after=after, limit=limit)
                )
            ),
        )

    def get_private_observation(
        self,
        game_id: str,
        player_id: str,
        *,
        manual_token: str,
    ) -> PlayerObservationResponse:
        """Return demo private observation for the session token holder."""
        return _wire_model(
            PlayerObservationResponse,
            self._not_found_as_resource(
                lambda: self._service().get_player_observation(
                    game_jobs.GetPlayerObservationQuery(
                        game_id=game_id,
                        player_id=player_id,
                        manual_token=manual_token,
                    )
                )
            ),
        )

    def submit_player_action(
        self,
        game_id: str,
        player_id: str,
        request: PlayerActionRequest,
        *,
        manual_token: str,
    ) -> PlayerActionResponse:
        """Submit one demo manual action."""
        return _wire_model(
            PlayerActionResponse,
            self._not_found_as_resource(
                lambda: self._service().submit_player_action(
                    game_jobs.PlayerActionCommand(
                        game_id=game_id,
                        player_id=player_id,
                        manual_token=manual_token,
                        **request.model_dump(mode="json"),
                    )
                )
            ),
        )

    def create_default_game(
        self,
        *,
        seed: int | None,
        manual_player_id: str | None,
    ) -> GameResponse:
        """Create a default-role demo game."""
        role_counts = self._settings.game_definitions.roles.default_counts_for(
            self._settings.game_default_player_count
        )
        return self.create_game(
            build_create_game_request(
                seed=seed,
                manual_player_id=manual_player_id,
                role_counts=role_counts,
            )
        )

    def _service(self) -> game_jobs.GameService:
        return game_jobs.GameService(
            game_jobs.GameUseCaseDependencies(
                repository=self._repository,
                config=build_game_usecase_config(self._settings),
                game_definitions=build_game_definitions(self._settings),
                llm_definitions=build_llm_definitions(self._settings),
                llm_provider_config=build_llm_provider_config(self._settings),
                telemetry=LoggingTelemetrySink(),
            )
        )

    @staticmethod
    def _not_found_as_resource(call: Callable[[], BaseModel]) -> BaseModel:
        try:
            return call()
        except (GameNotFoundError, InvalidGameIdError) as exc:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND) from exc


def _wire_model(model_type: type[TModel], source: BaseModel) -> TModel:
    return model_type.model_validate(source.model_dump(mode="json"))
