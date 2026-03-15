"""Web UI routes."""

from pathlib import Path

from fastapi_csrf_jinja.jinja_processor import csrf_token_processor
from starlette.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR),
    context_processors=[csrf_token_processor()],
)
