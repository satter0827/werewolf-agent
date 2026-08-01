"""Request-scoped FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Protocol, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from werewolf_agent.api.messages import DETAIL_REQUEST_RATE_LIMITED
from werewolf_agent.application import GameApplication, SetupApplication
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
    setups: SetupApplication
    message_max_chars: int
    diagnostics: AdminDiagnostics | None = None
    reveal_api_enabled: bool = False


def get_services() -> RequestServices:
    """Require bootstrap to provide request-scoped concrete adapters."""
    raise RuntimeError("API services are not configured.")


def get_public_setups() -> SetupApplication:
    """Require bootstrap to provide the persistence-free setup service."""
    raise RuntimeError("Public setup services are not configured.")


def get_owned_setups() -> SetupApplication | None:
    """Require bootstrap to provide optional authenticated setup persistence."""
    raise RuntimeError("Owned setup services are not configured.")


def get_optional_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal | None:
    """Authenticate a bearer token when present and otherwise return no principal."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
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


def get_principal(
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
) -> Principal:
    """Require one verified request principal."""
    if principal is None:
        raise AppError(
            "ログイン情報が必要です。",
            code=ErrorCode.AUTHENTICATION_REQUIRED,
        )
    return principal


ServicesDependency = Annotated[RequestServices, Depends(get_services)]
OptionalPrincipalDependency = Annotated[Principal | None, Depends(get_optional_principal)]
PrincipalDependency = Annotated[Principal, Depends(get_principal)]
PublicSetupsDependency = Annotated[SetupApplication, Depends(get_public_setups)]
OwnedSetupsDependency = Annotated[SetupApplication | None, Depends(get_owned_setups)]

__all__ = [
    "OptionalPrincipalDependency",
    "OwnedSetupsDependency",
    "PrincipalDependency",
    "PublicSetupsDependency",
    "RequestServices",
    "ServicesDependency",
    "get_optional_principal",
    "get_owned_setups",
    "get_principal",
    "get_public_setups",
    "get_services",
]
