"""Starlette middleware for request ID correlation and timing."""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from oopsie.logging import logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that adds request ID correlation and timing.

    - Extracts or generates an ``x-request-id`` header
    - Binds it via contextvars so every log line within the request includes it
    - Logs ``request_completed`` / ``request_failed`` with method, path,
      status code, and duration
    - Echoes the request_id back in the response header
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

        # Clear any leftover context from a previous request (connection reuse)
        # and bind the request_id so all downstream logs include it.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        response.headers["x-request-id"] = request_id
        return response
