"""Tests for oopsie.services.prompt_service."""

from oopsie.services.prompt_service import build_prompt


class TestBuildPrompt:
    def test_basic_prompt(self):
        """Produces same output as old _build_prompt for basic inputs."""
        result = build_prompt(
            error_class="ValueError",
            message="bad value",
            stack_trace="traceback line 1",
        )
        assert "ValueError" in result
        assert "bad value" in result
        assert "traceback line 1" in result

    def test_without_stack_trace(self):
        result = build_prompt(
            error_class="RuntimeError",
            message="oops",
            stack_trace=None,
        )
        assert "RuntimeError" in result
        assert "oops" in result

    def test_with_exception_chain(self):
        chain = [
            {
                "type": "ActiveRecord::RecordNotFound",
                "value": "Couldn't find User with id=99",
                "stacktrace": [
                    {
                        "file": "app/models/user.rb",
                        "function": "find_or_raise",
                        "lineno": 42,
                        "in_app": True,
                    },
                    {
                        "file": "activerecord/lib/core.rb",
                        "function": "find!",
                        "lineno": 331,
                        "in_app": False,
                    },
                ],
            },
            {
                "type": "AuthError",
                "value": "Login failed",
                "stacktrace": [
                    {
                        "file": "app/controllers/sessions.rb",
                        "function": "create",
                        "lineno": 18,
                        "in_app": True,
                    },
                ],
            },
        ]
        result = build_prompt(
            error_class="AuthError",
            message="Login failed",
            stack_trace="tb",
            exception_chain=chain,
        )
        assert "ActiveRecord::RecordNotFound" in result
        assert "Couldn't find User with id=99" in result
        assert "app/models/user.rb" in result
        assert "(app)" in result
        assert "AuthError" in result

    def test_exception_chain_excludes_raw_stack_trace(self):
        """When exception_chain is present, raw stack_trace is omitted."""
        chain = [{"type": "E", "value": "v", "stacktrace": [{"file": "f.rb"}]}]
        result = build_prompt(
            error_class="E",
            message="m",
            stack_trace="raw stack trace here",
            exception_chain=chain,
        )
        assert "raw stack trace here" not in result
        assert "Stack trace" not in result

    def test_falls_back_to_raw_stack_trace_without_chain(self):
        """Without exception_chain, raw stack_trace is included."""
        result = build_prompt(
            error_class="E",
            message="m",
            stack_trace="raw stack trace here",
        )
        assert "raw stack trace here" in result

    def test_with_execution_context_http(self):
        ctx = {
            "type": "http",
            "description": "POST /api/sessions",
            "data": {"method": "POST", "url": "/api/sessions"},
        }
        result = build_prompt(
            error_class="E",
            message="m",
            stack_trace=None,
            execution_context=ctx,
        )
        assert "POST /api/sessions" in result

    def test_with_execution_context_worker(self):
        ctx = {
            "type": "worker",
            "description": "UserMailer#welcome",
            "data": {"job_class": "UserMailer", "queue": "mailers"},
        }
        result = build_prompt(
            error_class="E",
            message="m",
            stack_trace=None,
            execution_context=ctx,
        )
        assert "UserMailer#welcome" in result
        assert "worker" in result.lower()

    def test_with_all_context(self):
        """Chain and context appear when all fields provided; raw stack omitted."""
        chain = [{"type": "E", "value": "v"}]
        ctx = {"type": "http", "description": "GET /health"}
        result = build_prompt(
            error_class="E",
            message="m",
            stack_trace="tb",
            exception_chain=chain,
            execution_context=ctx,
        )
        assert "tb" not in result  # raw stack trace excluded when chain present
        assert "GET /health" in result

    def test_without_context_matches_original(self):
        """Without new fields, output matches the original _build_prompt behavior."""
        result = build_prompt(
            error_class="ValueError",
            message="bad value",
            stack_trace="tb line 1",
        )
        assert "Error class: ValueError" in result
        assert "Message: bad value" in result
        assert "tb line 1" in result

    def test_exception_chain_without_stacktrace(self):
        """Chain entries without stacktrace still render."""
        chain = [{"type": "NoMethodError", "value": "undefined method 'foo'"}]
        result = build_prompt(
            error_class="NoMethodError",
            message="undefined method 'foo'",
            stack_trace=None,
            exception_chain=chain,
        )
        assert "NoMethodError" in result
        assert "undefined method 'foo'" in result

    def test_empty_exception_chain_falls_back_to_stack_trace(self):
        """Empty list [] is falsy — falls back to raw stack_trace."""
        result = build_prompt(
            error_class="E",
            message="m",
            stack_trace="raw trace here",
            exception_chain=[],
        )
        assert "raw trace here" in result
        assert "Exception chain" not in result
