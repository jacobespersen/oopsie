"""Prompt building for Claude Code fix attempts."""

import json
from typing import Any


def build_prompt(
    error_class: str,
    message: str,
    stack_trace: str | None,
    *,
    exception_chain: list[dict[str, Any]] | None = None,
    execution_context: dict[str, Any] | None = None,
) -> str:
    """Build a prompt instructing Claude to fix the bug.

    When exception_chain or execution_context are provided, appends
    additional context sections to the prompt.
    """
    parts = [
        "An error has been reported in this repository:",
        f"\nError class: {error_class}",
        f"Message: {message}",
    ]

    # Prefer structured exception chain over raw stack trace — including both
    # would be redundant noise for Claude.
    if exception_chain:
        parts.append(_format_exception_chain(exception_chain))
    elif stack_trace:
        parts.append(f"\nStack trace:\n```\n{stack_trace}\n```")

    if execution_context:
        parts.append(_format_execution_context(execution_context))

    parts.append(
        "\nFind the root cause in this codebase and fix it by editing the "
        "source files directly. You must use your tools to read the relevant "
        "files, then write or edit them to apply the fix. "
        "Make minimal, focused changes. Do not add unrelated improvements."
    )
    return "\n".join(parts)


def _format_exception_chain(chain: list[dict[str, Any]]) -> str:
    """Format the exception chain from root cause to outermost."""
    lines = ["\nException chain (root cause → outermost):"]
    for i, entry in enumerate(chain, 1):
        exc_type = entry.get("type", "Unknown")
        exc_value = entry.get("value", "")
        lines.append(f"  {i}. {exc_type}: {exc_value}")

        stacktrace = entry.get("stacktrace")
        if stacktrace:
            for frame in stacktrace:
                file = frame.get("file", "?")
                function = frame.get("function", "?")
                lineno = frame.get("lineno")
                in_app = frame.get("in_app", True)
                loc = f"{file}:{lineno}" if lineno else file
                tag = "(app)" if in_app else "(library)"
                lines.append(f"     at {loc} in {function} {tag}")

                # Include source context if available
                context_line = frame.get("context_line")
                if context_line:
                    lines.append(f"       > {context_line.strip()}")
    return "\n".join(lines)


def _format_execution_context(ctx: dict[str, Any]) -> str:
    """Format the execution context section."""
    ctx_type = ctx.get("type", "unknown")
    description = ctx.get("description")
    data = ctx.get("data")

    lines = [f"\nExecution context ({ctx_type}):"]
    if description:
        lines.append(f"  {description}")
    if data:
        lines.append(f"  {json.dumps(data, indent=2, default=str)}")
    return "\n".join(lines)
