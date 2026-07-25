"""Apply browser-safe headers to every API response."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

RequestHandler = Callable[[Request], Awaitable[Response]]


class ApiSecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Prevent caching, content sniffing, framing, and referrer disclosure."""

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        """Add the same security headers to successful and failed responses."""
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


__all__ = ["ApiSecurityHeadersMiddleware"]
