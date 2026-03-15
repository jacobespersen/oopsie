"""CSRF middleware extended to accept tokens from HTML form bodies."""

from starlette.requests import Request
from starlette_csrf import CSRFMiddleware


class FormCSRFMiddleware(CSRFMiddleware):
    """CSRFMiddleware extended to accept tokens from form fields.

    The upstream starlette-csrf only checks the ``x-csrftoken`` header.
    HTML forms cannot set custom headers, so this subclass also looks for
    the token in URL-encoded form bodies under the ``csrftoken`` field name.
    """

    async def _get_submitted_csrf_token(self, request: Request) -> str | None:
        # Check header first (API / fetch callers)
        header_token = request.headers.get(self.header_name)
        if header_token:
            return header_token

        # Fall back to form body for regular HTML form submissions
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type:
            form = await request.form()
            token = form.get(self.cookie_name)
            # Close the form to release the request body stream so
            # downstream handlers can read it again.
            await form.close()
            if token and isinstance(token, str):
                return token

        return None
