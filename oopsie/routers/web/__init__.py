"""Web UI routes."""

from pathlib import Path

from fastapi_csrf_jinja.jinja_processor import csrf_token_processor
from starlette.requests import Request
from starlette.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates"


def _org_slug_processor(request: Request) -> dict[str, str | None]:
    """Inject org_slug into every template from request.state (set by middleware)."""
    return {"org_slug": getattr(request.state, "org_slug", None)}


def _pending_signup_count_processor(request: Request) -> dict[str, int]:
    """Read pending signup request count from request.state for admin dot.

    The count is computed by the auth dependencies and stashed on
    request.state. This processor just reads it for template access.
    """
    return {
        "pending_signup_request_count": getattr(
            request.state, "pending_signup_request_count", 0
        )
    }


templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR),
    context_processors=[
        csrf_token_processor(),
        _org_slug_processor,
        _pending_signup_count_processor,
    ],
)
