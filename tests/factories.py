"""factory_boy factories for ORM model construction in tests."""

import factory
from oopsie.models.error import Error, ErrorStatus
from oopsie.models.fix_attempt import FixAttempt, FixAttemptStatus
from oopsie.models.github_installation import GithubInstallation, InstallationStatus
from oopsie.models.invitation import Invitation
from oopsie.models.membership import MemberRole, Membership
from oopsie.models.organization import Organization
from oopsie.models.project import Project
from oopsie.models.user import User
from oopsie.utils.encryption import hash_api_key


class OrganizationFactory(factory.Factory):
    class Meta:
        model = Organization

    name = factory.Sequence(lambda n: f"Org {n}")
    slug = factory.Sequence(lambda n: f"org-{n}")


class MembershipFactory(factory.Factory):
    class Meta:
        model = Membership

    role = MemberRole.member
    # organization_id and user_id must be supplied by the caller (for Membership)


class InvitationFactory(factory.Factory):
    class Meta:
        model = Invitation

    email = factory.Sequence(lambda n: f"invite-{n}@example.com")
    role = MemberRole.member
    invited_by_id = None
    # organization_id must be supplied by the caller


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


class GithubInstallationFactory(factory.Factory):
    class Meta:
        model = GithubInstallation

    github_installation_id = factory.Sequence(lambda n: 1000 + n)
    github_account_login = None
    status = InstallationStatus.ACTIVE
    # organization_id must be supplied by the caller
