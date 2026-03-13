"""Tests for oopsie.services.claude_service."""

from unittest.mock import patch

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKError,
    CLINotFoundError,
    ProcessError,
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

    async def test_cli_not_found_raises(self):
        with patch(_QUERY, side_effect=CLINotFoundError("not found")):
            with pytest.raises(ClaudeCodeError, match="CLI not found"):
                await run_claude_code("/repo", "E", "m", None, "key", 300)

    async def test_sdk_error_raises(self):
        with patch(_QUERY, side_effect=ClaudeSDKError("something broke")):
            with pytest.raises(ClaudeCodeError, match="Claude Code error"):
                await run_claude_code("/repo", "E", "m", None, "key", 300)

    async def test_timeout_raises(self):
        async def slow_query(**kwargs):
            import asyncio

            await asyncio.sleep(10)
            yield _text_message("too late")  # pragma: no cover

        with patch(_QUERY, return_value=slow_query()):
            with pytest.raises(ClaudeCodeError, match="timed out"):
                await run_claude_code("/repo", "E", "m", None, "key", 0)


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
