"""Process asynchronous game operations through application use cases."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast

from pydantic import BaseModel

from werewolf_agent.adapters.agents.game_driver import (
    AgentRuntime,
)
from werewolf_agent.adapters.agents.game_driver import (
    advance_game as advance_agent_game,
)
from werewolf_agent.adapters.supabase.json import jsonb
from werewolf_agent.adapters.supabase.llm_trace import SupabaseLlmTraceSink
from werewolf_agent.adapters.supabase.repository import (
    SupabaseDatabaseUnavailableError,
    SupabaseGameRepository,
    connect_worker_database,
)
from werewolf_agent.adapters.usecase_bridge import (
    build_game_definitions,
    build_game_usecase_config,
    build_llm_definitions,
    build_worker_llm_provider_config,
)
from werewolf_agent.configuration import AppSettings
from werewolf_agent.configuration.constants import EVENT_OUTCOME_FAILURE, EVENT_OUTCOME_SUCCESS
from werewolf_agent.configuration.messages import (
    LOG_WORKER_DATABASE_UNAVAILABLE,
    LOG_WORKER_REQUEST_CLAIMED,
    LOG_WORKER_REQUEST_COMPLETED,
    LOG_WORKER_REQUEST_FAILED,
    MESSAGE_GAME_PARTICIPATION_REQUIRED,
    MESSAGE_PAID_LLM_REQUIRES_MEMBER,
    MESSAGE_PLAYER_SEAT_NOT_OWNED,
    MESSAGE_SUPABASE_WORKER_DSN_REQUIRED,
    MESSAGE_WORKER_REQUEST_FAILED,
    message_unsupported_operation_type,
)
from werewolf_agent.contracts import (
    AppError,
    GameNotFoundError,
    InvalidGameIdError,
    problem_details_from_error,
    problem_details_from_spec,
)
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
from werewolf_agent.usecase import Actor, GameApplication
from werewolf_agent.usecase import handlers as usecases
from werewolf_agent.usecase._replay import checksum_payload
from werewolf_agent.usecase.models import (
    AdvanceGameCommand,
    GetGameQuery,
    UsecaseContext,
)

logger = logging.getLogger(__name__)
TModel = TypeVar("TModel", bound=BaseModel)


def run_worker_forever(settings: AppSettings) -> None:
    """Run the queue worker until the process is interrupted."""
    while True:
        try:
            processed = process_worker_batch(settings)
        except SupabaseDatabaseUnavailableError:
            logger.warning(
                LOG_WORKER_DATABASE_UNAVAILABLE,
                extra={
                    "event_action": LOG_WORKER_DATABASE_UNAVAILABLE,
                    "event_outcome": EVENT_OUTCOME_FAILURE,
                },
            )
            processed = 0
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
            logger.info(
                LOG_WORKER_REQUEST_CLAIMED,
                extra={
                    **_request_log_extra(request),
                    "event_action": LOG_WORKER_REQUEST_CLAIMED,
                    "event_outcome": EVENT_OUTCOME_SUCCESS,
                    "worker_id": settings.supabase_worker_id,
                },
            )
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
             or (
               status = 'running'
               and claimed_until < timezone('utc', now())
             )
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
        with connection.transaction():
            _execute_request(connection, settings, request)
    except Exception as exc:
        logger.exception(
            LOG_WORKER_REQUEST_FAILED,
            extra={
                **_request_log_extra(request),
                "event_action": LOG_WORKER_REQUEST_FAILED,
                "event_outcome": EVENT_OUTCOME_FAILURE,
            },
        )
        with connection.transaction():
            _fail_request(connection, request, _problem_from_exception(exc))


def _execute_request(
    connection: Any,
    settings: AppSettings,
    request: Mapping[str, Any],
) -> None:
    """Execute one claimed command inside a rollback-only savepoint."""
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
    result_payload = result.model_dump(mode="json")
    _record_accepted_command(connection, request, result_payload)
    _complete_request(connection, request, result_payload)


def _create_game(
    connection: Any,
    settings: AppSettings,
    request: Mapping[str, Any],
) -> GameResponse:
    payload = _json_object(request.get("request_payload"))
    create_request = CreateGameRequest.model_validate(payload)
    owner_user_id = str(request["owner_user_id"])
    llm_mode = _verified_creation_llm_mode(
        connection,
        owner_user_id=owner_user_id,
        requested_mode=str(request["llm_mode"]),
    )
    service = _service(
        connection,
        settings,
        owner_user_id=owner_user_id,
        create_llm_mode=llm_mode,
    )
    result = GameApplication(service).create(create_request)
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
    user_id = str(request["owner_user_id"])
    if not _game_participant_exists(connection, game_id=game_id, user_id=user_id):
        raise AppError(
            MESSAGE_GAME_PARTICIPATION_REQUIRED,
            code=ErrorCode.AUTHORIZATION_FAILED,
        )
    service = _service(connection, settings)
    runtime = AgentRuntime(
        config=build_worker_llm_provider_config(
            _game_llm_mode(connection, game_id),
            settings,
        ),
        definitions=build_llm_definitions(settings),
        trace_sink=SupabaseLlmTraceSink(
            connection,
            game_id=game_id,
            request_id=str(request["request_id"]),
            state_version=_expected_version(request),
        ),
    )
    result = advance_agent_game(
        service,
        AdvanceGameCommand(
            game_id=game_id,
            expected_version=_expected_version(request),
        ),
        runtime=runtime,
    )
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
    application = GameApplication(service)
    result = application.submit_action(
        game_id,
        Actor(user_id=user_id),
        action_request,
        _expected_version(request),
        player_id=player_id,
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
        observation = GameApplication(service).observation(
            game_id,
            Actor(user_id=str(participant["user_id"])),
            player_id,
        )
        connection.execute(
            """
            insert into private.game_player_observations (
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
                jsonb(observation.observation),
            ),
        )


def _materialize_reveal_view(
    connection: Any,
    settings: AppSettings,
    service: UsecaseContext,
    game_id: str,
) -> int:
    if not settings.reveal_api_enabled:
        connection.execute(
            """
            delete from private.game_reveals
            where game_id = %s
            """,
            (game_id,),
        )
        return _current_game_version(service, game_id)

    reveal = GameApplication(service).reveal(
        game_id,
        Actor(user_id="worker", is_admin=True),
    )
    reveal_response = _wire_model(GameRevealResponse, reveal)
    connection.execute(
        """
        insert into private.game_reveals (game_id, reveal_payload, state_version, updated_at)
        values (%s, %s, %s, timezone('utc', now()))
        on conflict (game_id) do update set
          reveal_payload = excluded.reveal_payload,
          state_version = excluded.state_version,
          updated_at = excluded.updated_at
        """,
        (game_id, jsonb(reveal_response.model_dump(mode="json")), reveal_response.version),
    )
    return reveal_response.version


def _current_game_version(service: UsecaseContext, game_id: str) -> int:
    game = usecases.get_game(GetGameQuery(game_id=game_id), dependencies=service)
    return int(game.state["version"])


def _service(
    connection: Any,
    settings: AppSettings,
    *,
    owner_user_id: str | None = None,
    create_llm_mode: Literal["fake", "paid"] = "fake",
) -> UsecaseContext:
    return UsecaseContext(
        repository=SupabaseGameRepository(connection, owner_user_id=owner_user_id),
        config=build_game_usecase_config(settings),
        game_definitions=build_game_definitions(settings),
        llm_definitions=build_llm_definitions(settings),
        create_llm_mode=create_llm_mode,
    )


def _expected_version(request: Mapping[str, Any]) -> int:
    value = request.get("expected_version")
    if value is None:
        payload = _json_object(request.get("request_payload"))
        value = payload.get("expected_version")
    if value is None:
        raise AppError(
            "expected_version is required.",
            code=ErrorCode.REQUEST_VALIDATION_FAILED,
        )
    return int(value)


def _verified_creation_llm_mode(
    connection: Any,
    *,
    owner_user_id: str,
    requested_mode: str,
) -> Literal["fake", "paid"]:
    if requested_mode not in {"fake", "paid"}:
        raise AppError(
            "The stored LLM mode is invalid.",
            code=ErrorCode.INTERNAL_UNEXPECTED,
        )
    row = connection.execute(
        """
        select is_anonymous
        from auth.users
        where id = %s
        limit 1
        """,
        (owner_user_id,),
    ).fetchone()
    if row is None:
        raise AppError(
            "利用者を確認できませんでした。",
            code=ErrorCode.AUTHENTICATION_REQUIRED,
        )
    if requested_mode == "paid" and bool(row["is_anonymous"]):
        raise AppError(
            MESSAGE_PAID_LLM_REQUIRES_MEMBER,
            code=ErrorCode.AUTHORIZATION_FAILED,
        )
    return cast(Literal["fake", "paid"], requested_mode)


def _game_llm_mode(connection: Any, game_id: str) -> str:
    row = connection.execute(
        """
        select llm_mode
        from public.games
        where game_id = %s
        limit 1
        """,
        (game_id,),
    ).fetchone()
    if row is None:
        raise AppError("ゲームが見つかりません。", code=ErrorCode.RESOURCE_NOT_FOUND)
    return str(row["llm_mode"])


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
          and participant_role in ('owner', 'player')
        limit 1
        """,
        (game_id, player_id, user_id),
    ).fetchone()
    return row is not None


def _game_participant_exists(
    connection: Any,
    *,
    game_id: str,
    user_id: str,
) -> bool:
    row = connection.execute(
        """
        select 1
        from public.game_participants
        where game_id = %s and user_id = %s
          and participant_role in ('owner', 'player', 'observer')
        limit 1
        """,
        (game_id, user_id),
    ).fetchone()
    return row is not None


def _complete_request(
    connection: Any,
    request: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> None:
    result = connection.execute(
        """
        update public.game_operation_requests
        set status = 'succeeded',
            result_payload = %s,
            completed_at = timezone('utc', now()),
            claimed_until = null
        where request_id = %s
          and status = 'running'
          and attempt_count = %s
          and worker_id = %s
        """,
        (
            jsonb(dict(result_payload)),
            request["request_id"],
            request["attempt_count"],
            request["worker_id"],
        ),
    )
    if getattr(result, "rowcount", 1) != 1:
        raise AppError(
            "操作の処理権限が更新されました。",
            code=ErrorCode.API_UNAVAILABLE,
            retryable=True,
        )
    logger.info(
        LOG_WORKER_REQUEST_COMPLETED,
        extra={
            **_request_log_extra(request),
            "game_id": str(result_payload.get("game_id") or request.get("game_id") or ""),
            "event_action": LOG_WORKER_REQUEST_COMPLETED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
        },
    )


def _record_accepted_command(
    connection: Any,
    request: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> None:
    state = _json_object(result_payload.get("state"))
    version = int(state.get("version") or 1)
    game_id = str(result_payload.get("game_id") or request.get("game_id") or "")
    payload = {
        "operation_type": str(request["operation_type"]),
        "expected_version": request.get("expected_version"),
        "player_id": request.get("player_id"),
        "request": _json_object(request.get("request_payload")),
    }
    connection.execute(
        """
        insert into private.accepted_commands (
          game_id, operation_id, version, command_type, actor_user_id, payload, checksum
        )
        values (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            game_id,
            request["request_id"],
            version,
            request["operation_type"],
            request["owner_user_id"],
            jsonb(payload),
            checksum_payload(payload),
        ),
    )
    _record_audit_event(
        connection,
        request,
        action="operation.succeeded",
        metadata={"game_id": game_id, "version": version},
    )


def _fail_request(
    connection: Any,
    request: Mapping[str, Any],
    problem: ProblemDetails,
) -> None:
    result = connection.execute(
        """
        update public.game_operation_requests
        set status = 'failed',
            error_payload = %s,
            completed_at = timezone('utc', now()),
            claimed_until = null
        where request_id = %s
          and status = 'running'
          and attempt_count = %s
          and worker_id = %s
        """,
        (
            jsonb(problem.model_dump(mode="json")),
            request["request_id"],
            request["attempt_count"],
            request["worker_id"],
        ),
    )
    if getattr(result, "rowcount", 1) != 1:
        return
    _record_audit_event(
        connection,
        request,
        action="operation.failed",
        metadata={"error_code": problem.code},
    )


def _record_audit_event(
    connection: Any,
    request: Mapping[str, Any],
    *,
    action: str,
    metadata: Mapping[str, Any],
) -> None:
    connection.execute(
        """
        insert into private.audit_events (
          actor_user_id, action, target_type, target_id, metadata
        )
        values (%s, %s, 'operation', %s, %s)
        """,
        (
            request["owner_user_id"],
            action,
            request["request_id"],
            jsonb(dict(metadata)),
        ),
    )


def _problem_from_exception(exc: Exception) -> ProblemDetails:
    if isinstance(exc, AppError):
        return problem_details_from_error(exc, instance="supabase-worker")
    if isinstance(exc, GameNotFoundError):
        code = ErrorCode.RESOURCE_NOT_FOUND
    elif isinstance(exc, InvalidGameIdError):
        code = ErrorCode.REQUEST_VALIDATION_FAILED
    else:
        code = ErrorCode.INTERNAL_UNEXPECTED
    return problem_details_from_spec(
        code,
        instance="supabase-worker",
        detail=MESSAGE_WORKER_REQUEST_FAILED if code is ErrorCode.INTERNAL_UNEXPECTED else None,
    )


def _wire_model(model_type: type[TModel], source: BaseModel) -> TModel:
    return model_type.model_validate(source.model_dump(mode="json"))


def _json_object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _request_log_extra(request: Mapping[str, Any]) -> dict[str, object]:
    return {
        "request_id": str(request.get("request_id") or ""),
        "operation_type": str(request.get("operation_type") or ""),
        "game_id": str(request.get("game_id") or ""),
        "attempt_count": int(request.get("attempt_count") or 0),
    }
