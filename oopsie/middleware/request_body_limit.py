"""ASGI middleware to reject request bodies exceeding a size limit."""

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from oopsie.logging import logger

# 1 MB in bytes
MAX_BODY_SIZE = 1_048_576


class RequestBodyLimitMiddleware:
    """Reject requests whose Content-Length exceeds MAX_BODY_SIZE.

    Checks the Content-Length header and rejects oversized requests
    early with 413. Applies to all HTTP routes. Chunked transfers
    without Content-Length are not blocked by this middleware — they
    are bounded by the field-level Pydantic validation limits.
    """

    def __init__(self, app: ASGIApp, max_body_size: int = MAX_BODY_SIZE) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
            except ValueError:
                response = JSONResponse(
                    {"detail": "Invalid Content-Length header"},
                    status_code=400,
                )
                await response(scope, receive, send)
                return

            if length < 0:
                response = JSONResponse(
                    {"detail": "Invalid Content-Length header"},
                    status_code=400,
                )
                await response(scope, receive, send)
                return

            if length > self.max_body_size:
                logger.warning(
                    "request_body_too_large",
                    content_length=length,
                    max_body_size=self.max_body_size,
                    path=request.url.path,
                )
                response = JSONResponse(
                    {"detail": "Request body too large"},
                    status_code=413,
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
