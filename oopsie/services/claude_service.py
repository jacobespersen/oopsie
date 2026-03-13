"""Claude Code SDK wrapper for generating fixes."""

import asyncio

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    CLINotFoundError,
    ProcessError,
    TextBlock,
    query,
)

from oopsie.logging import logger
from oopsie.services.exceptions import ClaudeCodeError


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

    options = ClaudeAgentOptions(
        permission_mode="bypassPermissions",
        cwd=repo_dir,
        max_turns=1,
        env={"ANTHROPIC_API_KEY": anthropic_api_key},
    )

    parts: list[str] = []
    try:
        async with asyncio.timeout(timeout_seconds):
            async for message_obj in query(prompt=prompt, options=options):
                if isinstance(message_obj, AssistantMessage):
                    for block in message_obj.content:
                        if isinstance(block, TextBlock):
                            parts.append(block.text)
    except TimeoutError:
        raise ClaudeCodeError(f"Claude Code timed out after {timeout_seconds}s")
    except ProcessError as exc:
        raise ClaudeCodeError(f"Claude Code failed: {exc}") from exc
    except CLINotFoundError as exc:
        raise ClaudeCodeError(f"Claude Code CLI not found: {exc}") from exc
    except ClaudeSDKError as exc:
        raise ClaudeCodeError(f"Claude Code error: {exc}") from exc

    output = "".join(parts).strip()
    logger.info("claude_code_completed", output_length=len(output))
    return output
