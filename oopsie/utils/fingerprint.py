"""Error fingerprinting for deduplication."""

import hashlib


def compute_fingerprint(
    error_class: str, message: str, stack_trace: str | None = None
) -> str:
    """Compute a deterministic fingerprint.

    Uses error_class, message, and first line of stack_trace.
    """
    first_line = ""
    if stack_trace:
        first_line = stack_trace.strip().split("\n")[0] if stack_trace.strip() else ""
    payload = f"{error_class}\n{message}\n{first_line}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:64]
