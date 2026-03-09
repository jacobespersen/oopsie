"""Structured logging setup with structlog.

Uses structlog backed by stdlib logging so that third-party libraries
(uvicorn, SQLAlchemy, etc.) are also formatted through the same pipeline.

Usage in any module:

    from oopsie.logging import logger
    logger.info("something_happened", key="value")
"""

import logging
import sys
import time
import uuid
from typing import cast

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Configure structlog and stdlib logging.

    Call once at startup (before the app is created) in main.py.

    Args:
        log_level: Root log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_format: "json" for production, "console" for pretty dev output.
    """
    # Processors that run on every log line — both ours and third-party.
    # Order matters: each processor enriches the event dict for the next.
    shared_processors: list[structlog.types.Processor] = [
        # Pull in any context bound via structlog.contextvars (e.g. request_id)
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
    ]

    if log_format == "console":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    # Configure structlog itself (for our logger.info() calls).
    # wrap_for_formatter hands off to stdlib's logging so everything
    # flows through a single StreamHandler below.
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # ProcessorFormatter intercepts stdlib LogRecords (from uvicorn,
    # SQLAlchemy, etc.) and runs them through the same processor chain
    # via foreign_pre_chain, so all output is consistently structured.
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    # Single handler writing to stdout — Docker/k8s captures stdout natively.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())

    # SQLAlchemy logs every SQL statement at INFO; WARNING still surfaces
    # connection errors and slow-query warnings.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str = "oopsie") -> structlog.stdlib.BoundLogger:
    """Return a structlog logger. Prefer importing ``logger`` directly."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


# Global logger instance — import this in other modules.
logger: structlog.stdlib.BoundLogger = get_logger()


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
