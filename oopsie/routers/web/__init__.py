"""Web UI routes."""

from pathlib import Path

from fastapi_csrf_jinja.jinja_processor import csrf_token_processor
from starlette.requests import Request
from starlette.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates"


def _org_slug_processor(request: Request) -> dict[str, str | None]:
    """Inject org_slug into every template from request.state (set by middleware)."""
    return {"org_slug": getattr(request.state, "org_slug", None)}


templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR),
    context_processors=[csrf_token_processor(), _org_slug_processor],
)
