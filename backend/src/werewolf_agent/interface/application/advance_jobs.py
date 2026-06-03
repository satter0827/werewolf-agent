"""Application bridge for API-side advance jobs."""

from __future__ import annotations

import logging
from typing import cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

import werewolf_agent.usecase.jobs as game_jobs
from werewolf_agent.commons.shared.constants import (
    EVENT_OUTCOME_FAILURE,
    EVENT_OUTCOME_SUCCESS,
)
from werewolf_agent.commons.shared.messages import (
    LOG_GAME_ADVANCE_JOB_COMPLETED,
    LOG_GAME_ADVANCE_JOB_FAILED,
    LOG_GAME_ADVANCE_JOB_STARTED,
    MESSAGE_ADVANCE_JOB_NOT_FOUND,
    MESSAGE_GAME_NOT_FOUND,
)
from werewolf_agent.contracts import (
    ACTIVE_ADVANCE_JOB_STATUSES,
    ADVANCE_JOB_STATUS_COMPLETED,
    ADVANCE_JOB_STATUS_FAILED,
    ADVANCE_JOB_STATUS_QUEUED,
    ADVANCE_JOB_STATUS_RUNNING,
    AppError,
    GameNotFoundError,
    InternalError,
    InvalidGameIdError,
    ResourceNotFoundError,
    problem_details_from_error,
)
from werewolf_agent.contracts.schemas import (
    AdvanceGameJobResponse,
    AdvanceGameResponse,
    AdvanceJobStatus,
    ProblemDetails,
)
from werewolf_agent.interface.application import games as game_application
from werewolf_agent.interface.application.database import SessionFactory, session_scope
from werewolf_agent.interface.application.models import GameAdvanceJobModel, GameModel, utc_now
from werewolf_agent.interface.runtime import AppSettings, get_observation_context
from werewolf_agent.interface.shared.constants import API_PREFIX
from werewolf_agent.interface.shared.log_levels import log_level_number

logger = logging.getLogger(__name__)


def start_advance_job(
    game_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> tuple[AdvanceGameJobResponse, bool]:
    """Create or return the active advance job for one game."""
    _ = settings
    with session_scope(session_factory) as session:
        game = session.get(GameModel, game_id)
        if game is None:
            raise ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND)
        active_job = _active_job(session, game_id)
        if active_job is not None:
            return _job_response(active_job), active_job.status == ADVANCE_JOB_STATUS_QUEUED

        now = utc_now()
        job = GameAdvanceJobModel(
            id=str(uuid4()),
            game_id=game.id,
            status=ADVANCE_JOB_STATUS_QUEUED,
            state_version=game.version,
            result=None,
            error=None,
            created_at=now,
            started_at=None,
            completed_at=None,
            updated_at=now,
        )
        session.add(job)
        session.flush()
        return _job_response(job), True


def get_advance_job(
    game_id: str,
    job_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> AdvanceGameJobResponse:
    """Return one persisted advance job."""
    _ = settings
    with session_scope(session_factory) as session:
        job = _job_by_game_and_id(session, game_id, job_id)
        if job is None:
            raise ResourceNotFoundError(MESSAGE_ADVANCE_JOB_NOT_FOUND)
        return _job_response(job)


def get_latest_advance_job(
    game_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> AdvanceGameJobResponse:
    """Return the latest persisted advance job for one game."""
    _ = settings
    with session_scope(session_factory) as session:
        statement = (
            select(GameAdvanceJobModel)
            .where(GameAdvanceJobModel.game_id == game_id)
            .order_by(GameAdvanceJobModel.created_at.desc())
            .limit(1)
        )
        job = session.scalars(statement).one_or_none()
        if job is None:
            raise ResourceNotFoundError(MESSAGE_ADVANCE_JOB_NOT_FOUND)
        return _job_response(job)


def run_advance_job(
    job_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> None:
    """Run one queued advance job in background."""
    game_id = _mark_job_running(job_id, session_factory=session_factory)
    if game_id is None:
        return

    try:
        prepared = _prepare_advance_game(
            game_id,
            session_factory=session_factory,
            settings=settings,
        )
        computed = _run_prepared_advance(
            prepared,
            session_factory=session_factory,
            settings=settings,
        )
        response = _commit_prepared_advance(
            computed,
            session_factory=session_factory,
            settings=settings,
        )
    except (GameNotFoundError, InvalidGameIdError):
        _mark_job_failed(
            job_id,
            ResourceNotFoundError(MESSAGE_GAME_NOT_FOUND),
            session_factory=session_factory,
        )
        logger.info(
            LOG_GAME_ADVANCE_JOB_FAILED,
            extra={
                "event_action": LOG_GAME_ADVANCE_JOB_FAILED,
                "event_outcome": EVENT_OUTCOME_FAILURE,
                "game_id": game_id,
                "job_id": job_id,
            },
        )
        return
    except AppError as exc:
        _mark_job_failed(job_id, exc, session_factory=session_factory)
        logger.log(
            _job_failure_level(exc),
            LOG_GAME_ADVANCE_JOB_FAILED,
            extra={
                **exc.log_extra(trace_id=_trace_id()),
                "event_action": LOG_GAME_ADVANCE_JOB_FAILED,
                "event_outcome": EVENT_OUTCOME_FAILURE,
                "game_id": game_id,
                "job_id": job_id,
            },
        )
        return
    except Exception:
        error = InternalError()
        _mark_job_failed(job_id, error, session_factory=session_factory)
        logger.exception(
            LOG_GAME_ADVANCE_JOB_FAILED,
            extra={
                **error.log_extra(trace_id=_trace_id()),
                "event_action": LOG_GAME_ADVANCE_JOB_FAILED,
                "event_outcome": EVENT_OUTCOME_FAILURE,
                "game_id": game_id,
                "job_id": job_id,
            },
        )
        return

    _mark_job_completed(job_id, response, session_factory=session_factory)
    logger.info(
        LOG_GAME_ADVANCE_JOB_COMPLETED,
        extra={
            "event_action": LOG_GAME_ADVANCE_JOB_COMPLETED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "game_id": response.game_id,
            "job_id": job_id,
            "game_status": response.status,
            "game_phase": response.state.get("phase"),
            "game_day": response.state.get("day"),
            "game_version": response.state.get("version"),
            "event_count": len(response.timeline),
        },
    )


def _prepare_advance_game(
    game_id: str,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> game_jobs.PreparedAdvanceGame:
    with session_scope(session_factory) as session:
        return game_application._use_cases(session, settings).prepare_advance_game(
            game_jobs.AdvanceGameCommand(game_id=game_id)
        )


def _run_prepared_advance(
    prepared: game_jobs.PreparedAdvanceGame,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> game_jobs.ComputedAdvanceGame:
    session = session_factory()
    try:
        return game_application._use_cases(session, settings).run_prepared_advance(prepared)
    finally:
        session.close()


def _commit_prepared_advance(
    computed: game_jobs.ComputedAdvanceGame,
    *,
    session_factory: SessionFactory,
    settings: AppSettings,
) -> game_jobs.AdvanceGameResult:
    with session_scope(session_factory) as session:
        return game_application._use_cases(session, settings).commit_prepared_advance(computed)


def _mark_job_running(
    job_id: str,
    *,
    session_factory: SessionFactory,
) -> str | None:
    with session_scope(session_factory) as session:
        job = _locked_job_by_id(session, job_id)
        if job is None or job.status != ADVANCE_JOB_STATUS_QUEUED:
            return None
        now = utc_now()
        job.status = ADVANCE_JOB_STATUS_RUNNING
        job.started_at = now
        job.updated_at = now
        logger.info(
            LOG_GAME_ADVANCE_JOB_STARTED,
            extra={
                "event_action": LOG_GAME_ADVANCE_JOB_STARTED,
                "event_outcome": EVENT_OUTCOME_SUCCESS,
                "game_id": job.game_id,
                "job_id": job.id,
                "state_version": job.state_version,
            },
        )
        return job.game_id


def _mark_job_completed(
    job_id: str,
    response: game_jobs.AdvanceGameResult,
    *,
    session_factory: SessionFactory,
) -> None:
    with session_scope(session_factory) as session:
        job = _locked_job_by_id(session, job_id)
        if job is None:
            return
        now = utc_now()
        job.status = ADVANCE_JOB_STATUS_COMPLETED
        job.result = response.model_dump(mode="json")
        job.error = None
        job.completed_at = now
        job.updated_at = now


def _mark_job_failed(
    job_id: str,
    error: AppError,
    *,
    session_factory: SessionFactory,
) -> None:
    with session_scope(session_factory) as session:
        job = _locked_job_by_id(session, job_id)
        if job is None:
            return
        now = utc_now()
        job.status = ADVANCE_JOB_STATUS_FAILED
        job.result = None
        job.error = _problem_details(error, job).model_dump(mode="json", exclude_none=True)
        job.completed_at = now
        job.updated_at = now


def _active_job(session: Session, game_id: str) -> GameAdvanceJobModel | None:
    statement = (
        select(GameAdvanceJobModel)
        .where(
            GameAdvanceJobModel.game_id == game_id,
            GameAdvanceJobModel.status.in_(ACTIVE_ADVANCE_JOB_STATUSES),
        )
        .order_by(GameAdvanceJobModel.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    return session.scalars(statement).one_or_none()


def _job_by_game_and_id(
    session: Session,
    game_id: str,
    job_id: str,
) -> GameAdvanceJobModel | None:
    statement = select(GameAdvanceJobModel).where(
        GameAdvanceJobModel.game_id == game_id,
        GameAdvanceJobModel.id == job_id,
    )
    return session.scalars(statement).one_or_none()


def _locked_job_by_id(session: Session, job_id: str) -> GameAdvanceJobModel | None:
    statement = (
        select(GameAdvanceJobModel).where(GameAdvanceJobModel.id == job_id).with_for_update()
    )
    return session.scalars(statement).one_or_none()


def _job_response(job: GameAdvanceJobModel) -> AdvanceGameJobResponse:
    return AdvanceGameJobResponse(
        job_id=job.id,
        game_id=job.game_id,
        status=cast(AdvanceJobStatus, job.status),
        state_version=job.state_version,
        poll_url=_poll_path(job.game_id, job.id),
        result=AdvanceGameResponse.model_validate(job.result) if job.result is not None else None,
        error=ProblemDetails.model_validate(job.error) if job.error is not None else None,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        updated_at=job.updated_at,
    )


def _problem_details(error: AppError, job: GameAdvanceJobModel) -> ProblemDetails:
    return problem_details_from_error(
        error,
        instance=_poll_path(job.game_id, job.id),
        trace_id=_trace_id(),
    )


def _poll_path(game_id: str, job_id: str) -> str:
    return f"{API_PREFIX}/games/{game_id}/advance-jobs/{job_id}"


def _trace_id() -> str | None:
    return get_observation_context().get("trace_id")


def _job_failure_level(error: AppError) -> int:
    return log_level_number(error.spec.log_level)
