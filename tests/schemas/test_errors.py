"""Tests for oopsie.schemas.errors."""

import pytest
from oopsie.schemas.errors import ErrorIngestBody
from pydantic import ValidationError


class TestErrorIngestBody:
    def test_minimal_payload(self):
        body = ErrorIngestBody(error_class="NoMethodError", message="oops")
        assert body.error_class == "NoMethodError"
        assert body.stack_trace is None
        assert body.exception_chain is None
        assert body.execution_context is None

    def test_with_all_fields(self):
        body = ErrorIngestBody(
            error_class="AuthError",
            message="Login failed",
            stack_trace="app/controllers/sessions.rb:18",
            exception_chain=[
                {"type": "ActiveRecord::RecordNotFound", "value": "Not found"},
                {"type": "AuthError", "value": "Login failed"},
            ],
            execution_context={
                "type": "http",
                "description": "POST /api/sessions",
                "data": {"method": "POST"},
            },
        )
        assert len(body.exception_chain) == 2
        assert body.execution_context.type == "http"

    def test_exception_chain_max_20(self):
        chain = [{"type": f"E{i}", "value": "v"} for i in range(21)]
        with pytest.raises(ValidationError):
            ErrorIngestBody(error_class="E", message="m", exception_chain=chain)

    def test_backwards_compatible(self):
        """Old-style payload with only required fields still works."""
        body = ErrorIngestBody(error_class="E", message="m")
        assert body.exception_chain is None
        assert body.execution_context is None
