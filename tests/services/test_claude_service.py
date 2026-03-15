"""Tests for oopsie.services.claude_service."""

from unittest.mock import patch

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    CLINotFoundError,
    ProcessError,
    ResultMessage,
    TextBlock,
)
from oopsie.services.claude_service import _build_prompt, run_claude_code
from oopsie.services.exceptions import ClaudeCodeError

_QUERY = "oopsie.services.claude_service.query"


async def _mock_query_yielding(messages):
    """Create an async generator that yields the given messages."""
    for msg in messages:
        yield msg


def _text_message(text: str) -> AssistantMessage:
    """Create an AssistantMessage with a single TextBlock."""
    block = TextBlock(text=text)
    return AssistantMessage(content=[block], model="claude-opus-4-6")


def _error_message(error_code: str, detail: str = "") -> AssistantMessage:
    """Create an AssistantMessage with an API error."""
    content = [TextBlock(text=detail)] if detail else []
    return AssistantMessage(content=content, model="<synthetic>", error=error_code)


def _result_message(
    *, is_error: bool = False, result: str | None = None
) -> ResultMessage:
    """Create a ResultMessage."""
    return ResultMessage(
        subtype="result",
        duration_ms=100,
        duration_api_ms=80,
        is_error=is_error,
        num_turns=1,
        session_id="test-session",
        result=result,
    )


@pytest.mark.asyncio
class TestRunClaudeCode:
    async def test_success(self):
        with patch(
            _QUERY,
            return_value=_mock_query_yielding(
                [_text_message("Fixed the bug in main.py")]
            ),
        ) as mock_query:
            output = await run_claude_code(
                "/repo", "ValueError", "bad value", "traceback", "sk-key", 300
            )
            assert output == "Fixed the bug in main.py"
            # Verify SDK was called with correct options
            call_kwargs = mock_query.call_args[1]
            assert "ValueError" in call_kwargs["prompt"]
            opts = call_kwargs["options"]
            assert opts.permission_mode == "bypassPermissions"
            assert opts.cwd == "/repo"
            assert opts.env["ANTHROPIC_API_KEY"] == "sk-key"

    async def test_sets_api_key_in_options(self):
        with patch(
            _QUERY, return_value=_mock_query_yielding([_text_message("done")])
        ) as mock_query:
            await run_claude_code("/repo", "E", "m", None, "sk-test-key", 300)
            opts = mock_query.call_args[1]["options"]
            assert opts.env["ANTHROPIC_API_KEY"] == "sk-test-key"

    async def test_joins_multiple_text_blocks(self):
        """Multiple AssistantMessages are concatenated."""
        with patch(
            _QUERY,
            return_value=_mock_query_yielding(
                [
                    _text_message("part1"),
                    _text_message("part2"),
                ]
            ),
        ):
            output = await run_claude_code("/repo", "E", "m", None, "key", 300)
            assert output == "part1part2"

    async def test_process_error_raises(self):
        with patch(_QUERY, side_effect=ProcessError("exit code 1")):
            with pytest.raises(ClaudeCodeError, match="Claude Code failed"):
                await run_claude_code("/repo", "E", "m", None, "key", 300)

    async def test_stderr_callback_is_set(self):
        """Verify the SDK options include a stderr callback for diagnostics."""
        with patch(
            _QUERY, return_value=_mock_query_yielding([_text_message("ok")])
        ) as mock_query:
            await run_claude_code("/repo", "E", "m", None, "key", 300)
            opts = mock_query.call_args[1]["options"]
            assert opts.stderr is not None and callable(opts.stderr)

    async def test_clears_nesting_guard_env(self):
        """CLAUDECODE env var is cleared so the CLI doesn't refuse to start."""
        with (
            patch.dict("os.environ", {"CLAUDECODE": "1"}),
            patch(
                _QUERY, return_value=_mock_query_yielding([_text_message("ok")])
            ) as mock_query,
        ):
            await run_claude_code("/repo", "E", "m", None, "key", 300)
            opts = mock_query.call_args[1]["options"]
            assert opts.env.get("CLAUDECODE") == ""

    async def test_clears_sse_port_env(self):
        """CLAUDE_CODE_SSE_PORT is cleared so the CLI runs standalone."""
        with (
            patch.dict("os.environ", {"CLAUDE_CODE_SSE_PORT": "12345"}),
            patch(
                _QUERY, return_value=_mock_query_yielding([_text_message("ok")])
            ) as mock_query,
        ):
            await run_claude_code("/repo", "E", "m", None, "key", 300)
            opts = mock_query.call_args[1]["options"]
            assert opts.env.get("CLAUDE_CODE_SSE_PORT") == ""

    async def test_cli_not_found_raises(self):
        with patch(_QUERY, side_effect=CLINotFoundError("not found")):
            with pytest.raises(ClaudeCodeError, match="CLI not found"):
                await run_claude_code("/repo", "E", "m", None, "key", 300)

    async def test_generic_exception_uses_stderr(self):
        """SDK re-raises ProcessError as plain Exception; stderr is still used."""
        captured_opts = {}

        async def _failing_gen(**kwargs):
            # Capture the options so we can invoke the stderr callback that
            # run_claude_code attached, then raise a plain Exception (which
            # is what the SDK does when it catches ProcessError internally).
            captured_opts.update(kwargs)
            opts = kwargs["options"]
            opts.stderr("real error detail from CLI")
            raise Exception("Command failed with exit code 1")
            yield  # make this an async generator  # pragma: no cover

        with patch(_QUERY, side_effect=_failing_gen):
            with pytest.raises(ClaudeCodeError, match="real error detail"):
                await run_claude_code("/repo", "E", "m", None, "key", 300)

    async def test_timeout_raises(self):
        async def slow_query(**kwargs):
            import asyncio

            await asyncio.sleep(10)
            yield _text_message("too late")  # pragma: no cover

        with patch(_QUERY, return_value=slow_query()):
            with pytest.raises(ClaudeCodeError, match="timed out"):
                await run_claude_code("/repo", "E", "m", None, "key", 0)

    # --- API error detection ---

    async def test_billing_error_raises_clear_message(self):
        """billing_error from AssistantMessage surfaces a user-friendly message."""
        messages = [
            _error_message("billing_error", "Credit balance is too low"),
            _result_message(is_error=True, result="Credit balance is too low"),
        ]
        with patch(_QUERY, return_value=_mock_query_yielding(messages)):
            with pytest.raises(
                ClaudeCodeError,
                match="API billing error: Credit balance is too low",
            ):
                await run_claude_code("/repo", "E", "m", None, "key", 300)

    async def test_auth_error_raises_clear_message(self):
        messages = [
            _error_message("authentication_failed", "Invalid API key"),
        ]
        with patch(_QUERY, return_value=_mock_query_yielding(messages)):
            with pytest.raises(
                ClaudeCodeError,
                match="API authentication failed: Invalid API key",
            ):
                await run_claude_code("/repo", "E", "m", None, "key", 300)

    async def test_rate_limit_error_raises_clear_message(self):
        messages = [
            _error_message("rate_limit", "Too many requests"),
        ]
        with patch(_QUERY, return_value=_mock_query_yielding(messages)):
            with pytest.raises(
                ClaudeCodeError,
                match="API rate limit exceeded: Too many requests",
            ):
                await run_claude_code("/repo", "E", "m", None, "key", 300)

    async def test_api_error_preferred_over_process_error(self):
        """When the SDK raises ProcessError after an API error, the clear
        API error message is used instead of the opaque process error."""

        async def _api_error_then_crash(**kwargs):
            yield _error_message("billing_error", "Credit balance is too low")
            raise ProcessError("exit code 1")

        with patch(_QUERY, side_effect=_api_error_then_crash):
            with pytest.raises(
                ClaudeCodeError,
                match="API billing error: Credit balance is too low",
            ):
                await run_claude_code("/repo", "E", "m", None, "key", 300)

    async def test_result_message_error_fallback(self):
        """ResultMessage.is_error is used when no AssistantMessage error."""
        messages = [
            _result_message(is_error=True, result="Something went wrong"),
        ]
        with patch(_QUERY, return_value=_mock_query_yielding(messages)):
            with pytest.raises(ClaudeCodeError, match="Something went wrong"):
                await run_claude_code("/repo", "E", "m", None, "key", 300)

    async def test_unknown_error_code_uses_raw_code(self):
        """Unknown error codes are passed through as-is."""
        messages = [
            _error_message("some_new_error", "details here"),
        ]
        with patch(_QUERY, return_value=_mock_query_yielding(messages)):
            with pytest.raises(ClaudeCodeError, match="some_new_error: details here"):
                await run_claude_code("/repo", "E", "m", None, "key", 300)


class TestBuildPrompt:
    def test_with_stack_trace(self):
        prompt = _build_prompt("ValueError", "bad value", "  File main.py, line 1")
        assert "ValueError" in prompt
        assert "bad value" in prompt
        assert "File main.py, line 1" in prompt
        assert "Stack trace" in prompt

    def test_without_stack_trace(self):
        prompt = _build_prompt("RuntimeError", "oops", None)
        assert "RuntimeError" in prompt
        assert "oops" in prompt
        assert "Stack trace" not in prompt
