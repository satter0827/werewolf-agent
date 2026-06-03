"""Protocol constants shared by interface adapters."""

from __future__ import annotations

from http import HTTPStatus
from typing import Final

API_PREFIX: Final = "/api/v1"
TRACE_ID_HEADER: Final = "X-Trace-Id"
REQUEST_ID_HEADER: Final = "X-Request-Id"
AUTHORIZATION_HEADER: Final = "Authorization"
BEARER_AUTH_SCHEME: Final = "Bearer"
PROBLEM_JSON_CONTENT_TYPE: Final = "application/problem+json"
HTTP_ACCEPTED: Final = HTTPStatus.ACCEPTED
HTTP_CREATED: Final = HTTPStatus.CREATED
