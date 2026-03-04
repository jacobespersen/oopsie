"""factory_boy factories for ORM model construction in tests."""

import factory
from oopsie.config import get_settings
from oopsie.models.error import Error, ErrorStatus
from oopsie.models.fix_attempt import FixAttempt, FixAttemptStatus
from oopsie.models.project import Project
from oopsie.models.user import User
from oopsie.utils.encryption import encrypt_value, hash_api_key


class UserFactory(factory.Factory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user-{n}@example.com")
    name = factory.Sequence(lambda n: f"User {n}")
    google_sub = factory.Sequence(lambda n: f"google-sub-{n}")
    avatar_url = None


class ProjectFactory(factory.Factory):
    class Meta:
        model = Project

    name = factory.Sequence(lambda n: f"project-{n}")
    github_repo_url = "https://github.com/o/r"
    github_token_encrypted = factory.LazyFunction(
        lambda: encrypt_value("ghp_t", get_settings().encryption_key)
    )
    api_key_hash = factory.Sequence(lambda n: hash_api_key(f"key-{n}"))
    default_branch = "main"
    error_threshold = 10


class ErrorFactory(factory.Factory):
    class Meta:
        model = Error

    error_class = "RuntimeError"
    message = factory.Sequence(lambda n: f"error message {n}")
    fingerprint = factory.Sequence(lambda n: f"fp-{n:06d}")
    status = ErrorStatus.OPEN
    stack_trace = None
    # project_id must be supplied by the caller


class FixAttemptFactory(factory.Factory):
    class Meta:
        model = FixAttempt

    branch_name = factory.Sequence(lambda n: f"oopsie/fix-{n:08x}")
    status = FixAttemptStatus.PENDING
    pr_url = None
    claude_output = None
    # error_id must be supplied by the caller
