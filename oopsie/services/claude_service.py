"""Claude Code SDK wrapper for generating fixes."""

import asyncio
import os

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    CLINotFoundError,
    ProcessError,
    ResultMessage,
    TextBlock,
    query,
)

from oopsie.logging import logger
from oopsie.services.exceptions import ClaudeCodeError

# Environment variables that interfere with standalone Claude Code sessions.
# The SDK merges os.environ into the child process, so these must be explicitly
# cleared when the worker is launched from inside VS Code or a Claude Code
# session (e.g. during local development).
# - CLAUDECODE: nesting guard that blocks nested sessions
# - CLAUDE_CODE_SSE_PORT: VS Code extension sets this to route the CLI through
#   its SSE transport; if inherited the child CLI connects to VS Code instead
#   of running standalone, causing an immediate exit-code-1 crash
_INHERITED_ENV_VARS_TO_CLEAR = ("CLAUDECODE", "CLAUDE_CODE_SSE_PORT")

# Maps SDK error codes on AssistantMessage.error to human-readable labels.
_API_ERROR_LABELS = {
    "billing_error": "API billing error",
    "authentication_failed": "API authentication failed",
    "rate_limit": "API rate limit exceeded",
    "invalid_request": "Invalid API request",
    "server_error": "Anthropic API server error",
}


def _build_prompt(error_class: str, message: str, stack_trace: str | None) -> str:
    """Build a prompt instructing Claude to fix the bug."""
    parts = [
        "You are debugging an application. An error has been reported:",
        f"\nError class: {error_class}",
        f"Message: {message}",
    ]
    if stack_trace:
        parts.append(f"\nStack trace:\n```\n{stack_trace}\n```")
    parts.append(
        "\nFind the root cause in this codebase and fix it. "
        "Make minimal, focused changes. Do not add unrelated improvements."
    )
    return "\n".join(parts)


def _build_clean_env(anthropic_api_key: str) -> dict[str, str]:
    """Build the env dict for the SDK, clearing interfering vars."""
    sdk_env: dict[str, str] = {"ANTHROPIC_API_KEY": anthropic_api_key}
    for var in _INHERITED_ENV_VARS_TO_CLEAR:
        if var in os.environ:
            sdk_env[var] = ""
    return sdk_env


def _make_stderr_collector(lines: list[str]):
    """Return a callback that collects stderr lines and logs them."""

    def _on_stderr(line: str) -> None:
        lines.append(line)
        logger.warning("claude_code_stderr", line=line.rstrip())

    return _on_stderr


async def run_claude_code(
    repo_dir: str,
    error_class: str,
    message: str,
    stack_trace: str | None,
    anthropic_api_key: str,
    timeout_seconds: int,
) -> str:
    """Run Claude Code on the repo via the Python SDK.

    Raises ClaudeCodeError on failure or timeout.
    """
    prompt = _build_prompt(error_class, message, stack_trace)
    sdk_env = _build_clean_env(anthropic_api_key)

    logger.info(
        "claude_code_starting",
        repo_dir=repo_dir,
        prompt_length=len(prompt),
        timeout_seconds=timeout_seconds,
    )

    stderr_lines: list[str] = []
    options = ClaudeAgentOptions(
        permission_mode="bypassPermissions",
        cwd=repo_dir,
        env=sdk_env,
        stderr=_make_stderr_collector(stderr_lines),
        # OS-level sandbox restricts writes to cwd only (Seatbelt on macOS,
        # bubblewrap on Linux). Prevents Claude from modifying files outside
        # the cloned repo directory.
        sandbox={
            "enabled": True,
            "autoAllowBashIfSandboxed": True,
            "allowUnsandboxedCommands": False,
        },
    )

    parts: list[str] = []
    # Track API-level errors reported inside the SDK message stream.
    # These arrive as AssistantMessage.error / ResultMessage.is_error *before*
    # the process exits, so we capture them here and use them to build a
    # clear error message instead of the opaque ProcessError that follows.
    api_error: str | None = None

    try:
        async with asyncio.timeout(timeout_seconds):
            async for message_obj in query(prompt=prompt, options=options):
                if isinstance(message_obj, AssistantMessage):
                    if message_obj.error:
                        # The text blocks contain the human-readable detail
                        # (e.g. "Credit balance is too low").
                        detail = " ".join(
                            block.text
                            for block in message_obj.content
                            if isinstance(block, TextBlock)
                        ).strip()
                        label = _API_ERROR_LABELS.get(
                            message_obj.error, message_obj.error
                        )
                        api_error = f"{label}: {detail}" if detail else label
                        logger.error(
                            "claude_code_api_error",
                            error_code=message_obj.error,
                            detail=detail,
                        )
                    else:
                        for block in message_obj.content:
                            if isinstance(block, TextBlock):
                                parts.append(block.text)

                elif isinstance(message_obj, ResultMessage):
                    if message_obj.is_error and not api_error:
                        # Fallback: ResultMessage carries an error we didn't
                        # already capture from AssistantMessage.
                        api_error = (
                            message_obj.result or "Claude Code returned an error"
                        )
                        logger.error(
                            "claude_code_result_error",
                            result=message_obj.result,
                            stop_reason=message_obj.stop_reason,
                        )

    except TimeoutError:
        raise ClaudeCodeError(f"Claude Code timed out after {timeout_seconds}s")
    except (ProcessError, CLINotFoundError, ClaudeSDKError, Exception) as exc:
        # If we already captured a clear API error from the message stream,
        # prefer that over the opaque SDK/process error.
        if api_error:
            logger.error("claude_code_failed", error=api_error)
            raise ClaudeCodeError(api_error) from exc

        stderr_output = "".join(stderr_lines).strip()
        detail = stderr_output or str(exc)
        logger.error(
            "claude_code_failed",
            error=detail,
            exception_type=type(exc).__name__,
        )
        if isinstance(exc, CLINotFoundError):
            raise ClaudeCodeError(f"Claude Code CLI not found: {exc}") from exc
        raise ClaudeCodeError(f"Claude Code failed: {detail}") from exc

    # The stream completed without an exception, but we may still have
    # captured an API error (the SDK sometimes exits cleanly after errors).
    if api_error:
        raise ClaudeCodeError(api_error)

    output = "".join(parts).strip()
    logger.info("claude_code_completed", output_length=len(output))
    return output
