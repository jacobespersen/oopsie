"""Tests for oopsie.services.github_service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from oopsie.exceptions import (
    GitHubApiError,
    GitOperationError,
)
from oopsie.services.github_service import (
    _git_env,
    clone_repo,
    commit_and_push,
    create_branch,
    create_pull_request,
    has_changes,
    parse_repo_owner_name,
)

_EXEC = "oopsie.services.github_service.asyncio.create_subprocess_exec"


def _make_process(
    returncode: int = 0,
    stdout: bytes = b"",
    stderr: bytes = b"",
):
    """Create a mock subprocess."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


def test_git_env_disables_credential_caching():
    env = _git_env()
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_TERMINAL_PROMPT"] == "0"


@pytest.mark.asyncio
async def test_credential_helper_arg_passed():
    """Verify _run_git passes -c credential.helper= to disable caching."""
    proc = _make_process()
    with patch(_EXEC, return_value=proc) as mock_exec:
        await clone_repo("https://github.com/o/r", "tok", "main", "/tmp/d")
        args = mock_exec.call_args[0]
        assert args[1] == "-c"
        assert args[2] == "credential.helper="


@pytest.mark.asyncio
class TestRunGit:
    async def test_clone_repo_calls_git_clone(self):
        proc = _make_process()
        with patch(_EXEC, return_value=proc) as mock_exec:
            await clone_repo(
                "https://github.com/o/r",
                "tok123",
                "main",
                "/tmp/dest",
            )
            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert args[0] == "git"
            assert "clone" in args
            assert "--depth" in args
            assert "." == args[-1]

    async def test_clone_repo_injects_token(self):
        proc = _make_process()
        with patch(_EXEC, return_value=proc) as mock_exec:
            await clone_repo(
                "https://github.com/o/r",
                "tok123",
                "main",
                "/tmp/dest",
            )
            args = mock_exec.call_args[0]
            url_arg = [a for a in args if "x-access-token" in str(a)]
            assert len(url_arg) == 1
            assert "tok123" in url_arg[0]

    async def test_clone_repo_raises_on_failure(self):
        proc = _make_process(returncode=128, stderr=b"fatal: repo not found")
        with patch(_EXEC, return_value=proc):
            with pytest.raises(GitOperationError, match="git clone failed"):
                await clone_repo(
                    "https://github.com/o/r",
                    "tok",
                    "main",
                    "/tmp/dest",
                )

    async def test_create_branch(self):
        proc = _make_process()
        with patch(_EXEC, return_value=proc) as mock_exec:
            await create_branch("/repo", "oopsie/fix-abc123")
            args = mock_exec.call_args[0]
            assert "checkout" in args
            assert "-b" in args
            assert "oopsie/fix-abc123" in args

    async def test_has_changes_true(self):
        proc = _make_process(stdout=b" M src/main.py\n")
        with patch(_EXEC, return_value=proc):
            assert await has_changes("/repo") is True

    async def test_has_changes_false(self):
        proc = _make_process(stdout=b"")
        with patch(_EXEC, return_value=proc):
            assert await has_changes("/repo") is False

    async def test_commit_and_push(self):
        proc = _make_process()
        calls = []

        async def fake_exec(*args, **kwargs):
            calls.append(args)
            return proc

        with patch(_EXEC, side_effect=fake_exec):
            await commit_and_push(
                "/repo",
                "fix-branch",
                "fix: something",
                "tok",
                "https://github.com/o/r",
            )
            assert len(calls) == 3
            assert "add" in calls[0]
            assert "commit" in calls[1]
            assert "push" in calls[2]

    async def test_commit_and_push_raises_on_push_failure(self):
        success_proc = _make_process()
        fail_proc = _make_process(returncode=1, stderr=b"push rejected")
        call_count = 0

        async def fake_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return fail_proc if call_count == 3 else success_proc

        with patch(_EXEC, side_effect=fake_exec):
            with pytest.raises(GitOperationError, match="git push failed"):
                await commit_and_push(
                    "/repo",
                    "fix-branch",
                    "msg",
                    "tok",
                    "https://github.com/o/r",
                )


_CLIENT = "oopsie.services.github_service.httpx.AsyncClient"


@pytest.mark.asyncio
class TestCreatePullRequest:
    async def test_create_pr_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"html_url": "https://github.com/o/r/pull/1"}

        with patch(_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_client

            url = await create_pull_request(
                "o",
                "r",
                "tok",
                "fix-branch",
                "main",
                "title",
                "body",
            )
            assert url == "https://github.com/o/r/pull/1"
            mock_client.post.assert_called_once()

    async def test_create_pr_failure(self):
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.text = "Validation Failed"

        with patch(_CLIENT) as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_client

            with pytest.raises(GitHubApiError, match="422"):
                await create_pull_request(
                    "o",
                    "r",
                    "tok",
                    "fix-branch",
                    "main",
                    "t",
                    "b",
                )


class TestParseRepoOwnerName:
    def test_https_url(self):
        result = parse_repo_owner_name("https://github.com/owner/repo")
        assert result == ("owner", "repo")

    def test_https_url_with_git_suffix(self):
        result = parse_repo_owner_name("https://github.com/owner/repo.git")
        assert result == ("owner", "repo")

    def test_trailing_slash(self):
        result = parse_repo_owner_name("https://github.com/owner/repo/")
        assert result == ("owner", "repo")

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            parse_repo_owner_name("https://github.com/only-owner")
