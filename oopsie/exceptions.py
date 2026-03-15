"""Application-wide exception classes."""


class NoInvitationError(Exception):
    """Raised when a new user attempts to register without a pending invitation."""


class OopsieServiceError(Exception):
    """Base exception for service-layer errors."""


class GitOperationError(OopsieServiceError):
    """Raised when a git CLI operation fails."""


class ClaudeCodeError(OopsieServiceError):
    """Raised when Claude Code CLI fails or times out."""


class GitHubApiError(OopsieServiceError):
    """Raised when GitHub REST API call fails."""


class GitHubAppNotConfiguredError(OopsieServiceError):
    """Raised when GitHub App credentials are not configured."""


class AnthropicKeyNotConfiguredError(OopsieServiceError):
    """Raised when no Anthropic API key is configured for a project or its org."""


class AlreadyHasOrganizationError(OopsieServiceError):
    """Raised when a user already belongs to an organization."""


class DuplicateInvitationError(OopsieServiceError):
    """Raised when a user already has a pending invitation."""
