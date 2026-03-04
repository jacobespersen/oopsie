"""Tests for oopsie.services.claude_service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from oopsie.services.claude_service import _build_prompt, run_claude_code
from oopsie.services.exceptions import ClaudeCodeError

_EXEC = "oopsie.services.claude_service.asyncio.create_subprocess_exec"
_WAIT = "oopsie.services.claude_service.asyncio.wait_for"


def _make_process(
    returncode: int = 0,
    stdout: bytes = b"",
    stderr: bytes = b"",
):
    """Create a mock subprocess."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = AsyncMock()
    return proc


@pytest.mark.asyncio
class TestRunClaudeCode:
    async def test_success(self):
        proc = _make_process(stdout=b"Fixed the bug in main.py")
        with patch(_EXEC, return_value=proc) as mock_exec:
            output = await run_claude_code(
                "/repo",
                "ValueError",
                "bad value",
                "traceback",
                "sk-key",
                300,
            )
            assert output == "Fixed the bug in main.py"
            args = mock_exec.call_args[0]
            assert args[0] == "claude"
            assert "--print" in args
            assert "--dangerously-skip-permissions" in args

    async def test_sets_api_key_in_env(self):
        proc = _make_process(stdout=b"done")
        with patch(_EXEC, return_value=proc) as mock_exec:
            await run_claude_code("/repo", "E", "m", None, "sk-test-key", 300)
            kwargs = mock_exec.call_args[1]
            assert kwargs["env"]["ANTHROPIC_API_KEY"] == "sk-test-key"

    async def test_nonzero_exit_raises(self):
        proc = _make_process(returncode=1, stderr=b"something went wrong")
        with patch(_EXEC, return_value=proc):
            with pytest.raises(ClaudeCodeError, match="Claude Code failed"):
                await run_claude_code("/repo", "E", "m", None, "key", 300)

    async def test_timeout_raises(self):
        proc = _make_process()
        proc.kill = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch(_EXEC, return_value=proc):
            with patch(_WAIT, side_effect=TimeoutError()):
                with pytest.raises(ClaudeCodeError, match="timed out"):
                    await run_claude_code("/repo", "E", "m", None, "key", 5)
                proc.kill.assert_called_once()


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
