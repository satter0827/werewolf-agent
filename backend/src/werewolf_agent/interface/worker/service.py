"""Supabase request queue worker."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any, TypeVar

from psycopg.types.json import Jsonb
from pydantic import BaseModel

import werewolf_agent.usecase.jobs as game_jobs
from werewolf_agent.commons.shared.messages import (
    MESSAGE_PLAYER_SEAT_NOT_OWNED,
    MESSAGE_SUPABASE_WORKER_DSN_REQUIRED,
    MESSAGE_WORKER_REQUEST_FAILED,
    message_unsupported_operation_type,
)
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    AdvanceGameResponse,
    CreateGameRequest,
    GameResponse,
    GameRevealResponse,
    PlayerActionRequest,
    PlayerActionResponse,
    ProblemDetails,
)
from werewolf_agent.interface.application.settings import (
    build_game_definitions,
    build_game_usecase_config,
    build_llm_definitions,
    build_llm_provider_config,
)
from werewolf_agent.interface.application.telemetry import LoggingTelemetrySink
from werewolf_agent.interface.runtime import AppSettings
from werewolf_agent.interface.worker.llm_trace import SupabaseLlmTraceSink
from werewolf_agent.interface.worker.repository import (
    SupabaseGameRepository,
    connect_worker_database,
)

logger = logging.getLogger(__name__)
TModel = TypeVar("TModel", bound=BaseModel)


def run_worker_forever(settings: AppSettings) -> None:
    """Run the queue worker until the process is interrupted."""
    while True:
        processed = process_worker_batch(settings)
        if processed == 0:
            time.sleep(settings.supabase_worker_poll_interval_seconds)


def process_worker_batch(settings: AppSettings) -> int:
    """Claim and process at most one configured batch of requests."""
    if not settings.supabase_worker_configured:
        raise AppError(MESSAGE_SUPABASE_WORKER_DSN_REQUIRED)
    processed = 0
    with connect_worker_database(settings.supabase_db_dsn_value) as connection:
        for _ in range(settings.supabase_worker_batch_size):
            with connection.transaction():
                request = _claim_request(connection, settings)
                if request is None:
                    break
                _process_request(connection, settings, request)
                processed += 1
    return processed


def _claim_request(connection: Any, settings: AppSettings) -> dict[str, Any] | None:
    row = connection.execute(
        """
        with next_request as (
          select request_id
          from public.game_operation_requests
          where status = 'queued'
            and (claimed_until is null or claimed_until < timezone('utc', now()))
          order by created_at
          for update skip locked
          limit 1
        )
        update public.game_operation_requests r
        set status = 'running',
            worker_id = %s,
            attempt_count = attempt_count + 1,
            started_at = coalesce(started_at, timezone('utc', now())),
            claimed_until = timezone('utc', now()) + make_interval(secs => %s)
        where r.request_id = (select request_id from next_request)
        returning *
        """,
        (settings.supabase_worker_id, settings.supabase_worker_claim_seconds),
    ).fetchone()
    return dict(row) if row is not None else None


def _process_request(
    connection: Any,
    settings: AppSettings,
    request: Mapping[str, Any],
) -> None:
    try:
        operation_type = str(request["operation_type"])
        result: BaseModel
        if operation_type == "create_game":
            result = _create_game(connection, settings, request)
        elif operation_type == "advance_game":
            result = _advance_game(connection, settings, request)
        elif operation_type == "submit_action":
            result = _submit_action(connection, settings, request)
        else:
            raise AppError(message_unsupported_operation_type(operation_type))
        _complete_request(connection, request, result.model_dump(mode="json"))
    except Exception as exc:
        logger.exception("worker request failed", extra={"request_id": request.get("request_id")})
        _fail_request(connection, request, _problem_from_exception(exc))


def _create_game(
    connection: Any,
    settings: AppSettings,
    request: Mapping[str, Any],
) -> GameResponse:
    payload = _json_object(request.get("request_payload"))
    create_request = CreateGameRequest.model_validate(payload)
    owner_user_id = str(request["owner_user_id"])
    service = _service(connection, settings, owner_user_id=owner_user_id)
    result = service.create_game(_create_command(create_request, settings))
    response = _wire_model(GameResponse, result)
    participant_player_id = create_request.manual_player_id or "observer"
    _insert_participant(
        connection,
        game_id=response.game_id,
        user_id=owner_user_id,
        player_id=participant_player_id,
        role="owner" if create_request.manual_player_id is None else "player",
    )
    _materialize_private_views(connection, settings, response.game_id)
    return response


def _advance_game(
    connection: Any,
    settings: AppSettings,
    request: Mapping[str, Any],
) -> AdvanceGameResponse:
    game_id = str(request.get("game_id") or "")
    service = _service(
        connection,
        settings,
        request_id=str(request["request_id"]),
        game_id=game_id,
    )
    result = service.advance_game(game_jobs.AdvanceGameCommand(game_id=game_id))
    response = _wire_model(AdvanceGameResponse, result)
    _materialize_private_views(connection, settings, response.game_id)
    return response


def _submit_action(
    connection: Any,
    settings: AppSettings,
    request: Mapping[str, Any],
) -> PlayerActionResponse:
    game_id = str(request.get("game_id") or "")
    player_id = str(request.get("player_id") or "")
    user_id = str(request["owner_user_id"])
    if not _participant_exists(connection, game_id=game_id, player_id=player_id, user_id=user_id):
        raise AppError(
            MESSAGE_PLAYER_SEAT_NOT_OWNED,
            code=ErrorCode.AUTHORIZATION_FAILED,
        )
    action_request = PlayerActionRequest.model_validate(
        _json_object(request.get("request_payload"))
    )
    service = _service(connection, settings)
    result = service.submit_player_action(
        game_jobs.PlayerActionCommand(
            game_id=game_id,
            player_id=player_id,
            trusted_user_id=user_id,
            **action_request.model_dump(mode="json"),
        )
    )
    response = _wire_model(PlayerActionResponse, result)
    _materialize_private_views(connection, settings, response.game_id)
    return response


def _materialize_private_views(connection: Any, settings: AppSettings, game_id: str) -> None:
    service = _service(connection, settings)
    state_version = _materialize_reveal_view(connection, settings, service, game_id)
    participants = connection.execute(
        """
        select user_id, player_id
        from public.game_participants
        where game_id = %s and participant_role in ('owner', 'player')
        """,
        (game_id,),
    ).fetchall()
    for participant in participants:
        player_id = str(participant["player_id"])
        if player_id == "observer":
            continue
        observation = service.get_player_observation(
            game_jobs.GetPlayerObservationQuery(
                game_id=game_id,
                player_id=player_id,
                trusted_user_id=str(participant["user_id"]),
            )
        )
        connection.execute(
            """
            insert into public.game_player_observations (
              game_id, player_id, user_id, state_version, observation, updated_at
            )
            values (%s, %s, %s, %s, %s, timezone('utc', now()))
            on conflict (game_id, player_id, user_id) do update set
              state_version = excluded.state_version,
              observation = excluded.observation,
              updated_at = excluded.updated_at
            """,
            (
                game_id,
                player_id,
                participant["user_id"],
                state_version,
                Jsonb(observation.observation),
            ),
        )


def _materialize_reveal_view(
    connection: Any,
    settings: AppSettings,
    service: game_jobs.GameService,
    game_id: str,
) -> int:
    if not settings.reveal_api_enabled:
        connection.execute(
            """
            delete from public.game_reveals
            where game_id = %s
            """,
            (game_id,),
        )
        return _current_game_version(service, game_id)

    reveal = service.get_game_reveal(game_jobs.GetGameRevealQuery(game_id=game_id))
    reveal_response = _wire_model(GameRevealResponse, reveal)
    connection.execute(
        """
        insert into public.game_reveals (game_id, reveal_payload, state_version, updated_at)
        values (%s, %s, %s, timezone('utc', now()))
        on conflict (game_id) do update set
          reveal_payload = excluded.reveal_payload,
          state_version = excluded.state_version,
          updated_at = excluded.updated_at
        """,
        (game_id, Jsonb(reveal_response.model_dump(mode="json")), reveal_response.version),
    )
    return reveal_response.version


def _current_game_version(service: game_jobs.GameService, game_id: str) -> int:
    game = service.get_game(game_jobs.GetGameQuery(game_id=game_id))
    return int(game.state["version"])


def _service(
    connection: Any,
    settings: AppSettings,
    *,
    owner_user_id: str | None = None,
    request_id: str | None = None,
    game_id: str | None = None,
) -> game_jobs.GameService:
    return game_jobs.GameService(
        game_jobs.GameUseCaseDependencies(
            repository=SupabaseGameRepository(connection, owner_user_id=owner_user_id),
            config=build_game_usecase_config(settings),
            game_definitions=build_game_definitions(settings),
            llm_definitions=build_llm_definitions(settings),
            llm_provider_config=build_llm_provider_config(settings),
            telemetry=LoggingTelemetrySink(),
            llm_trace_sink=SupabaseLlmTraceSink(
                connection,
                game_id=game_id,
                request_id=request_id,
            ),
        )
    )


def _create_command(
    request: CreateGameRequest,
    settings: AppSettings,
) -> game_jobs.CreateGameCommand:
    return game_jobs.CreateGameCommand(
        seed=request.seed,
        role_counts=request.role_counts,
        manual_player_id=request.manual_player_id,
        rules=request.rules or settings.game_definitions.rules.local_rules,
        scenario_id=request.scenario_id,
        setup_preset_id=request.setup_preset_id,
        narration_mode=request.narration_mode or settings.game_default_narration_mode,
        character_assignments=request.character_assignments,
        custom_roles=[item for item in request.custom_roles],
        custom_characters=[item for item in request.custom_characters],
    )


def _insert_participant(
    connection: Any,
    *,
    game_id: str,
    user_id: str,
    player_id: str,
    role: str,
) -> None:
    connection.execute(
        """
        insert into public.game_participants (game_id, user_id, player_id, participant_role)
        values (%s, %s, %s, %s)
        on conflict (game_id, user_id, player_id) do nothing
        """,
        (game_id, user_id, player_id, role),
    )


def _participant_exists(
    connection: Any,
    *,
    game_id: str,
    player_id: str,
    user_id: str,
) -> bool:
    row = connection.execute(
        """
        select 1
        from public.game_participants
        where game_id = %s and player_id = %s and user_id = %s
        limit 1
        """,
        (game_id, player_id, user_id),
    ).fetchone()
    return row is not None


def _complete_request(
    connection: Any,
    request: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> None:
    connection.execute(
        """
        update public.game_operation_requests
        set status = 'completed',
            result_payload = %s,
            completed_at = timezone('utc', now()),
            claimed_until = null
        where request_id = %s
        """,
        (Jsonb(dict(result_payload)), request["request_id"]),
    )


def _fail_request(
    connection: Any,
    request: Mapping[str, Any],
    problem: ProblemDetails,
) -> None:
    connection.execute(
        """
        update public.game_operation_requests
        set status = 'failed',
            error_payload = %s,
            completed_at = timezone('utc', now()),
            claimed_until = null
        where request_id = %s
        """,
        (Jsonb(problem.model_dump(mode="json")), request["request_id"]),
    )


def _problem_from_exception(exc: Exception) -> ProblemDetails:
    if isinstance(exc, AppError):
        code = exc.code.value
        detail = exc.detail
    else:
        code = ErrorCode.INTERNAL_UNEXPECTED.value
        detail = MESSAGE_WORKER_REQUEST_FAILED
    return ProblemDetails(
        type=f"urn:werewolf-agent:error:{code}",
        title=MESSAGE_WORKER_REQUEST_FAILED,
        status=500,
        detail=detail,
        instance="supabase-worker",
        code=code,
    )


def _wire_model(model_type: type[TModel], source: BaseModel) -> TModel:
    return model_type.model_validate(source.model_dump(mode="json"))


def _json_object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}
