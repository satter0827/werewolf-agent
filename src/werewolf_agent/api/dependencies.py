"""Request-scoped FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Protocol, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from werewolf_agent.api.messages import DETAIL_REQUEST_RATE_LIMITED
from werewolf_agent.application import GameApplication
from werewolf_agent.application.operations import AccessPolicy, OperationQueue
from werewolf_agent.contracts import AppError, ErrorCode
from werewolf_agent.security.principal import AuthenticationError, Principal

_bearer = HTTPBearer(auto_error=False)


class _Authenticator(Protocol):
    def authenticate(self, token: str) -> Principal: ...


class AdminDiagnostics(Protocol):
    """Private diagnostic reads available only to administrator routes."""

    def operation(self, operation_id: str) -> Mapping[str, Any] | None: ...

    def traces(self, game_id: str, *, limit: int) -> list[Mapping[str, Any]]: ...

    def usage(self, game_id: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class RequestServices:
    """Request-scoped application services."""

    games: GameApplication
    operations: OperationQueue
    access: AccessPolicy
    message_max_chars: int
    diagnostics: AdminDiagnostics | None = None
    reveal_api_enabled: bool = True


def get_services() -> RequestServices:
    """Require bootstrap to provide request-scoped concrete adapters."""
    raise RuntimeError("API services are not configured.")


def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    """Authenticate one request without exposing the bearer token downstream."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(
            "ログイン情報が必要です。",
            code=ErrorCode.AUTHENTICATION_REQUIRED,
        )
    try:
        authenticator = cast(_Authenticator, request.app.state.authenticator)
        principal = authenticator.authenticate(credentials.credentials)
    except AuthenticationError as exc:
        raise AppError(
            str(exc),
            code=ErrorCode.AUTHENTICATION_REQUIRED,
        ) from exc
    if not request.app.state.principal_rate_limiter.allow(
        user_id=principal.user_id,
        path=request.url.path,
    ):
        raise AppError(
            DETAIL_REQUEST_RATE_LIMITED,
            code=ErrorCode.REQUEST_RATE_LIMITED,
        )
    return principal


ServicesDependency = Annotated[RequestServices, Depends(get_services)]
PrincipalDependency = Annotated[Principal, Depends(get_principal)]

__all__ = [
    "PrincipalDependency",
    "RequestServices",
    "ServicesDependency",
    "get_principal",
    "get_services",
]
