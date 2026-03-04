"""Custom exception hierarchy for Oopsie services."""


class OopsieServiceError(Exception):
    """Base exception for service-layer errors."""


class GitOperationError(OopsieServiceError):
    """Raised when a git CLI operation fails."""


class ClaudeCodeError(OopsieServiceError):
    """Raised when Claude Code CLI fails or times out."""


class GitHubApiError(OopsieServiceError):
    """Raised when GitHub REST API call fails."""
