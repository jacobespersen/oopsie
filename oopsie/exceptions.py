"""Application-wide exception classes."""


class NoInvitationError(Exception):
    """Raised when a new user attempts to register without a pending invitation."""
