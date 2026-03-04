"""Claude Code CLI subprocess wrapper."""

import asyncio
import os

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
    """Run Claude Code CLI on the repo. Returns Claude's stdout output.

    Raises ClaudeCodeError on failure or timeout.
    """
    prompt = _build_prompt(error_class, message, stack_trace)
    env = {**os.environ}
    if anthropic_api_key:
        env["ANTHROPIC_API_KEY"] = anthropic_api_key
    proc = await asyncio.create_subprocess_exec(
        "claude",
        "--print",
        "--dangerously-skip-permissions",
        "-p",
        prompt,
        cwd=repo_dir,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_seconds
        )
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        raise ClaudeCodeError(f"Claude Code timed out after {timeout_seconds}s")
    if proc.returncode != 0:
        raise ClaudeCodeError(
            f"Claude Code failed (rc={proc.returncode}): {stderr.decode().strip()}"
        )
    output = stdout.decode().strip()
    logger.info("claude_code_completed", output_length=len(output))
    return output
