"""Process asynchronous game operations through application handlers."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Mapping
from typing import Any, Literal, TypeVar

from pydantic import BaseModel

from werewolf_agent.adapters.agents.game_driver import (
    AgentRuntime,
    drive_prepared_game,
)
from werewolf_agent.adapters.application_bridge import (
    build_game_application_config,
    build_llm_definitions,
    build_worker_llm_provider_config,
)
from werewolf_agent.adapters.supabase.llm_trace import (
    BufferedLlmTraceSink,
    SupabaseLlmTraceSink,
)
from werewolf_agent.adapters.supabase.operations import SupabaseAccessPolicy
from werewolf_agent.adapters.supabase.pool import (
    SupabaseDatabaseUnavailableError,
    borrow_database_connection,
    create_database_pool,
    open_database_pool,
)
from werewolf_agent.adapters.supabase.repository import (
    SupabaseGameRepository,
)
from werewolf_agent.adapters.supabase.worker_store import SupabaseWorkerStore
from werewolf_agent.application import (
    Actor,
    ApplicationContext,
    CreateGameCommand,
    GameApplication,
    PlayerActionCommand,
)
from werewolf_agent.contracts import (
    AppError,
    GameNotFoundError,
    InvalidGameIdError,
    problem_details_from_error,
    problem_details_from_spec,
)
from werewolf_agent.contracts.error_catalog import get_error_spec
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.mapping import wire_model
from werewolf_agent.contracts.schemas import (
    AdvanceGameResponse,
    GameResponse,
    GameRevealResponse,
    PlayerActionRequest,
    PlayerActionResponse,
    ProblemDetails,
)
from werewolf_agent.observability.constants import (
    EVENT_OUTCOME_FAILURE,
    EVENT_OUTCOME_SUCCESS,
)
from werewolf_agent.observability.levels import log_level_number
from werewolf_agent.settings import AppSettings
from werewolf_agent.worker.composition import WorkerDependencies
from werewolf_agent.worker.events import (
    LOG_WORKER_APPLICATION_STOPPED,
    LOG_WORKER_DATABASE_UNAVAILABLE,
    LOG_WORKER_REQUEST_CLAIMED,
    LOG_WORKER_REQUEST_COMPLETED,
    LOG_WORKER_REQUEST_FAILED,
    LOG_WORKER_REQUEST_RETRY_EXHAUSTED,
    LOG_WORKER_REQUEST_RETRY_SCHEDULED,
    LOG_WORKER_REQUEST_RETRY_STARTED,
)
from werewolf_agent.worker.messages import (
    MESSAGE_SUPABASE_WORKER_DSN_REQUIRED,
    MESSAGE_WORKER_REQUEST_FAILED,
    message_unsupported_operation_type,
)

logger = logging.getLogger(__name__)
TModel = TypeVar("TModel", bound=BaseModel)


def run_worker_forever(
    settings: AppSettings,
    *,
    dependencies: WorkerDependencies,
) -> None:
    """Run the queue worker until the process is interrupted."""
    pool = _worker_pool(settings)
    try:
        open_database_pool(pool, timeout=settings.supabase_pool_timeout_seconds)
        while True:
            try:
                processed = process_worker_batch(
                    settings,
                    dependencies=dependencies,
                    pool=pool,
                )
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
    finally:
        try:
            pool.close()
        except Exception:
            logger.exception(
                "worker.application.stop_failed",
                extra={
                    "event_action": "worker.application.stop_failed",
                    "event_outcome": EVENT_OUTCOME_FAILURE,
                    "error_code": ErrorCode.INTERNAL_UNEXPECTED.value,
                },
            )
            raise
        logger.info(
            LOG_WORKER_APPLICATION_STOPPED,
            extra={
                "event_action": LOG_WORKER_APPLICATION_STOPPED,
                "event_outcome": EVENT_OUTCOME_SUCCESS,
                "worker_mode": "run",
            },
        )


def process_worker_batch(
    settings: AppSettings,
    *,
    dependencies: WorkerDependencies,
    pool: Any | None = None,
) -> int:
    """Claim and process at most one configured batch of requests."""
    if not settings.supabase_worker_configured:
        raise AppError(MESSAGE_SUPABASE_WORKER_DSN_REQUIRED)
    if pool is None:
        owned_pool = _worker_pool(settings)
        try:
            open_database_pool(
                owned_pool,
                timeout=settings.supabase_pool_timeout_seconds,
            )
            return process_worker_batch(
                settings,
                dependencies=dependencies,
                pool=owned_pool,
            )
        finally:
            owned_pool.close()
    with borrow_database_connection(pool) as connection:
        store = SupabaseWorkerStore(connection)
        with connection.transaction():
            requests = store.claim_requests(
                worker_id=settings.supabase_worker_id,
                claim_seconds=settings.supabase_worker_claim_seconds,
                quantity=settings.supabase_worker_batch_size,
            )
    processed = 0
    for request in requests:
        logger.info(
            LOG_WORKER_REQUEST_CLAIMED,
            extra={
                **_request_log_extra(request),
                "event_action": LOG_WORKER_REQUEST_CLAIMED,
                "event_outcome": EVENT_OUTCOME_SUCCESS,
                "worker_id": settings.supabase_worker_id,
            },
        )
        if int(request.get("attempt_count") or 0) > settings.supabase_worker_max_attempts:
            problem = problem_details_from_spec(
                ErrorCode.OPERATION_RETRY_EXHAUSTED,
                instance="supabase-worker",
            )
            with borrow_database_connection(pool) as connection, connection.transaction():
                SupabaseWorkerStore(connection).fail_request(request, problem)
            logger.error(
                LOG_WORKER_REQUEST_RETRY_EXHAUSTED,
                extra={
                    **_request_log_extra(request),
                    "event_action": LOG_WORKER_REQUEST_RETRY_EXHAUSTED,
                    "event_outcome": EVENT_OUTCOME_FAILURE,
                    "error_code": ErrorCode.OPERATION_RETRY_EXHAUSTED.value,
                    "error_message": problem.detail,
                },
            )
            processed += 1
            continue
        _process_request(pool, settings, dependencies, request)
        processed += 1
    return processed


def _worker_pool(settings: AppSettings) -> Any:
    """Return the closed process-owned worker pool."""
    return create_database_pool(
        settings.supabase_db_dsn_value,
        min_size=settings.supabase_worker_pool_min_size,
        max_size=settings.supabase_worker_pool_max_size,
        timeout=settings.supabase_pool_timeout_seconds,
        name="werewolf-worker",
    )


def _process_request(
    pool: Any,
    settings: AppSettings,
    dependencies: WorkerDependencies,
    request: Mapping[str, Any],
) -> None:
    try:
        if str(request["operation_type"]) == "advance_game":
            _execute_advance_request(pool, settings, dependencies, request)
        else:
            with borrow_database_connection(pool) as connection, connection.transaction():
                _execute_request(
                    connection,
                    SupabaseWorkerStore(connection),
                    settings,
                    dependencies,
                    request,
                )
    except Exception as exc:
        problem = _problem_from_exception(exc)
        attempt_count = int(request.get("attempt_count") or 0)
        retry = _is_retryable(exc) and attempt_count < settings.supabase_worker_max_attempts
        log_extra = {
            **_request_log_extra(request),
            "event_outcome": EVENT_OUTCOME_FAILURE,
            "error_code": problem.code,
            "error_message": problem.detail,
        }
        if retry:
            if attempt_count <= 1:
                logger.warning(
                    LOG_WORKER_REQUEST_RETRY_STARTED,
                    extra={
                        **log_extra,
                        "event_action": LOG_WORKER_REQUEST_RETRY_STARTED,
                    },
                )
            logger.debug(
                LOG_WORKER_REQUEST_RETRY_SCHEDULED,
                extra={
                    **log_extra,
                    "event_action": LOG_WORKER_REQUEST_RETRY_SCHEDULED,
                },
            )
        else:
            level = (
                log_level_number(get_error_spec(exc.code).log_level)
                if isinstance(exc, AppError)
                else logging.ERROR
            )
            logger.log(
                level,
                LOG_WORKER_REQUEST_FAILED,
                exc_info=level >= logging.ERROR,
                extra={**log_extra, "event_action": LOG_WORKER_REQUEST_FAILED},
            )
        with borrow_database_connection(pool) as connection, connection.transaction():
            store = SupabaseWorkerStore(connection)
            if retry:
                store.retry_request(request, problem)
            else:
                store.fail_request(request, problem)


def _execute_request(
    connection: Any,
    store: SupabaseWorkerStore,
    settings: AppSettings,
    dependencies: WorkerDependencies,
    request: Mapping[str, Any],
) -> None:
    """Execute one claimed command inside a rollback-only savepoint."""
    operation_type = str(request["operation_type"])
    result: BaseModel
    if operation_type == "create_game":
        result = _create_game(connection, store, settings, dependencies, request)
    elif operation_type == "submit_action":
        result = _submit_action(connection, store, settings, dependencies, request)
    else:
        raise AppError(message_unsupported_operation_type(operation_type))
    _complete_result(store, request, result)


def _complete_result(
    store: SupabaseWorkerStore,
    request: Mapping[str, Any],
    result: BaseModel,
) -> None:
    """Commit ledger, audit, and queue completion for one result."""
    result_payload = result.model_dump(mode="json")
    store.record_accepted_command(request, result_payload)
    store.complete_request(request, result_payload)
    logger.info(
        LOG_WORKER_REQUEST_COMPLETED,
        extra={
            **_request_log_extra(request),
            "game_id": str(result_payload.get("game_id") or request.get("game_id") or ""),
            "event_action": LOG_WORKER_REQUEST_COMPLETED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
        },
    )


def _execute_advance_request(
    pool: Any,
    settings: AppSettings,
    dependencies: WorkerDependencies,
    request: Mapping[str, Any],
) -> None:
    """Run the Agent decision pipeline without retaining a database transaction."""
    game_id = str(request.get("game_id") or "")
    user_id = str(request["owner_user_id"])
    with borrow_database_connection(pool) as connection, connection.transaction():
        context = _service(connection, settings, dependencies)
        application = GameApplication(
            context,
            access_policy=SupabaseAccessPolicy(connection),
        )
        prepared = application.prepare_advance(
            game_id,
            Actor(user_id=user_id),
            _expected_version(request),
        )
        store = SupabaseWorkerStore(connection)
        llm_mode = store.game_llm_mode(game_id)

    traces = BufferedLlmTraceSink()
    runtime = AgentRuntime(
        config=build_worker_llm_provider_config(llm_mode, settings),
        definitions=build_llm_definitions(settings),
        trace_sink=traces,
        agent_factories=dependencies.agent_factories,
    )
    with _LeaseHeartbeat(pool, settings, request) as heartbeat:
        driven = drive_prepared_game(
            prepared,
            runtime=runtime,
        )
        computed = application.compute_advance(driven)
        heartbeat.require_owned()

        with borrow_database_connection(pool) as connection, connection.transaction():
            store = SupabaseWorkerStore(connection)
            context = _service(connection, settings, dependencies)
            result = GameApplication(
                context,
                access_policy=SupabaseAccessPolicy(connection),
            ).commit_advance(Actor(user_id=user_id), computed)
            response = _wire_model(AdvanceGameResponse, result)
            traces.flush_to(
                SupabaseLlmTraceSink(
                    connection,
                    game_id=game_id,
                    request_id=str(request["request_id"]),
                    state_version=_expected_version(request),
                )
            )
            _materialize_private_views(
                connection,
                store,
                settings,
                dependencies,
                response.game_id,
                actor_user_id=user_id,
            )
            _complete_result(store, request, response)


class _LeaseHeartbeat:
    """Renew one PGMQ visibility timeout while the Agent pipeline is running."""

    def __init__(self, pool: Any, settings: AppSettings, request: Mapping[str, Any]) -> None:
        self._pool = pool
        self._interval = settings.supabase_worker_heartbeat_seconds
        self._claim_seconds = settings.supabase_worker_claim_seconds
        self._request = request
        self._stopped = threading.Event()
        self._lost = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> _LeaseHeartbeat:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stopped.set()
        self._thread.join(timeout=float(self._interval))

    def require_owned(self) -> None:
        """Fail before commit if the queue visibility lease was lost."""
        if self._lost.is_set():
            raise AppError(
                "操作の処理権限を維持できませんでした。",
                code=ErrorCode.API_UNAVAILABLE,
                retryable=True,
            )

    def _run(self) -> None:
        while not self._stopped.wait(self._interval):
            try:
                with borrow_database_connection(self._pool) as connection, connection.transaction():
                    renewed = SupabaseWorkerStore(connection).renew_claim(
                        self._request,
                        claim_seconds=self._claim_seconds,
                    )
                if not renewed:
                    self._lost.set()
                    return
            except Exception:
                self._lost.set()
                return


def _create_game(
    connection: Any,
    store: SupabaseWorkerStore,
    settings: AppSettings,
    dependencies: WorkerDependencies,
    request: Mapping[str, Any],
) -> GameResponse:
    payload = _json_object(request.get("request_payload"))
    create_command = CreateGameCommand.model_validate(payload)
    owner_user_id = str(request["owner_user_id"])
    llm_mode = store.verify_creation_llm_mode(
        owner_user_id=owner_user_id,
        requested_mode=str(request["llm_mode"]),
    )
    service = _service(
        connection,
        settings,
        dependencies,
        owner_user_id=owner_user_id,
        create_llm_mode=llm_mode,
    )
    result = GameApplication(service).create(
        create_command.model_copy(update={"llm_mode": llm_mode})
    )
    response = _wire_model(GameResponse, result)
    participant_player_id = create_command.manual_player_id or "observer"
    store.add_participant(
        game_id=response.game_id,
        user_id=owner_user_id,
        player_id=participant_player_id,
        role="owner" if create_command.manual_player_id is None else "player",
    )
    _materialize_private_views(
        connection,
        store,
        settings,
        dependencies,
        response.game_id,
        actor_user_id=owner_user_id,
    )
    return response


def _submit_action(
    connection: Any,
    store: SupabaseWorkerStore,
    settings: AppSettings,
    dependencies: WorkerDependencies,
    request: Mapping[str, Any],
) -> PlayerActionResponse:
    game_id = str(request.get("game_id") or "")
    player_id = str(request.get("player_id") or "")
    user_id = str(request["owner_user_id"])
    action_request = PlayerActionRequest.model_validate(
        _json_object(request.get("request_payload"))
    )
    service = _service(connection, settings, dependencies)
    application = GameApplication(service, access_policy=SupabaseAccessPolicy(connection))
    result = application.submit_action(
        Actor(user_id=user_id),
        PlayerActionCommand(
            game_id=game_id,
            player_id=player_id,
            type=action_request.type,
            ability_id=action_request.ability_id,
            target_id=action_request.target_id,
            message=action_request.message,
            reason=action_request.reason,
            expected_version=_expected_version(request),
        ),
    )
    response = _wire_model(PlayerActionResponse, result)
    _materialize_private_views(
        connection,
        store,
        settings,
        dependencies,
        response.game_id,
        actor_user_id=user_id,
    )
    return response


def _materialize_private_views(
    connection: Any,
    store: SupabaseWorkerStore,
    settings: AppSettings,
    dependencies: WorkerDependencies,
    game_id: str,
    *,
    actor_user_id: str,
) -> None:
    service = _service(connection, settings, dependencies)
    state_version = _materialize_reveal_view(
        connection,
        store,
        settings,
        service,
        game_id,
        actor_user_id=actor_user_id,
    )
    for participant in store.player_participants(game_id):
        observation = GameApplication(
            service,
            access_policy=SupabaseAccessPolicy(connection),
        ).observation(
            game_id,
            Actor(user_id=participant.user_id),
            participant.player_id,
        )
        store.save_observation(
            game_id=game_id,
            participant=participant,
            state_version=state_version,
            observation=observation.observation,
        )


def _materialize_reveal_view(
    connection: Any,
    store: SupabaseWorkerStore,
    settings: AppSettings,
    service: ApplicationContext,
    game_id: str,
    *,
    actor_user_id: str,
) -> int:
    if not settings.reveal_api_enabled:
        store.delete_reveal(game_id)
        public_game = GameApplication(
            service,
            access_policy=SupabaseAccessPolicy(connection),
        ).get(
            game_id,
            Actor(user_id=actor_user_id),
        )
        return int(public_game.state["version"])

    reveal = GameApplication(service).reveal(
        game_id,
        Actor(user_id="worker", is_admin=True),
    )
    reveal_response = _wire_model(GameRevealResponse, reveal)
    store.save_reveal(
        game_id=game_id,
        payload=reveal_response.model_dump(mode="json"),
        version=reveal_response.version,
    )
    return reveal_response.version


def _service(
    connection: Any,
    settings: AppSettings,
    dependencies: WorkerDependencies,
    *,
    owner_user_id: str | None = None,
    create_llm_mode: Literal["fake", "paid"] = "fake",
) -> ApplicationContext:
    return ApplicationContext(
        repository=SupabaseGameRepository(connection, owner_user_id=owner_user_id),
        config=build_game_application_config(settings),
        create_llm_mode=create_llm_mode,
        rule_packs=dependencies.rule_packs,
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


def _is_retryable(exc: Exception) -> bool:
    """Return whether a failed operation may be safely redelivered."""
    if isinstance(exc, AppError):
        return exc.retryable
    return isinstance(exc, SupabaseDatabaseUnavailableError)


def _wire_model(model_type: type[TModel], source: BaseModel) -> TModel:
    return wire_model(model_type, source)


def _json_object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _request_log_extra(request: Mapping[str, Any]) -> dict[str, object]:
    return {
        "request_id": str(request.get("request_id") or ""),
        "operation_type": str(request.get("operation_type") or ""),
        "game_id": str(request.get("game_id") or ""),
        "attempt_count": int(request.get("attempt_count") or 0),
    }
