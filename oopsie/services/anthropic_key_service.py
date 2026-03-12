"""Service for managing encrypted Anthropic API keys on orgs and projects."""

from cryptography.fernet import InvalidToken

from oopsie.logging import logger
from oopsie.models.organization import Organization
from oopsie.models.project import Project
from oopsie.services.exceptions import AnthropicKeyNotConfiguredError
from oopsie.utils.encryption import decrypt_value, encrypt_value


def set_anthropic_api_key(
    entity: Organization | Project, plaintext_key: str, encryption_key: str
) -> None:
    """Encrypt and store an Anthropic API key on an org or project."""
    entity.anthropic_api_key_encrypted = encrypt_value(plaintext_key, encryption_key)


def get_anthropic_api_key(
    entity: Organization | Project, encryption_key: str
) -> str | None:
    """Decrypt and return the Anthropic API key, or None if not set or corrupt."""
    if not entity.anthropic_api_key_encrypted:
        return None
    try:
        return decrypt_value(entity.anthropic_api_key_encrypted, encryption_key)
    except InvalidToken:
        logger.error(
            "anthropic_key_decryption_failed",
            entity_type=type(entity).__name__,
            entity_id=str(entity.id),
        )
        return None


def clear_anthropic_api_key(entity: Organization | Project) -> None:
    """Remove the stored Anthropic API key."""
    entity.anthropic_api_key_encrypted = None


def mask_anthropic_api_key(plaintext: str) -> str:
    """Return a masked version of the key showing only the last 4 chars.

    Example: "sk-ant-api03-abcdefghijk" -> "sk---------hijk"
    """
    if len(plaintext) <= 4:
        return "sk-\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
    return f"sk-\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022{plaintext[-4:]}"


def resolve_anthropic_api_key(project: Project, encryption_key: str) -> str:
    """Resolve the Anthropic API key for a project.

    Resolution order: project key -> org key -> error.
    Expects project.organization to be eagerly loaded.
    """
    # Check project-level key first
    project_key = get_anthropic_api_key(project, encryption_key)
    if project_key:
        return project_key

    # Fall back to org-level key
    org_key = get_anthropic_api_key(project.organization, encryption_key)
    if org_key:
        return org_key

    raise AnthropicKeyNotConfiguredError(
        f"No Anthropic API key configured for project {project.id} or its organization."
    )
