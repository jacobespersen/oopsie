"""Git CLI and GitHub REST API operations."""

import asyncio
import os
from urllib.parse import urlparse

import httpx

from oopsie.logging import logger
from oopsie.services.exceptions import GitHubApiError, GitOperationError


def _git_env() -> dict[str, str]:
    """Build env for git subprocesses with credential caching disabled."""
    env = os.environ.copy()
    # Prevent the credential helper from caching tokens in the system keychain
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


async def _run_git(*args: str, cwd: str) -> str:
    """Run a git command and return stdout. Raises GitOperationError on failure."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-c",
        "credential.helper=",
        *args,
        cwd=cwd,
        env=_git_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise GitOperationError(
            f"git {args[0]} failed (rc={proc.returncode}): {stderr.decode().strip()}"
        )
    return stdout.decode().strip()


def _inject_token_into_url(repo_url: str, token: str) -> str:
    """Inject a token into a GitHub HTTPS URL for authenticated operations."""
    parsed = urlparse(repo_url)
    return parsed._replace(netloc=f"x-access-token:{token}@{parsed.hostname}").geturl()


async def clone_repo(repo_url: str, token: str, branch: str, dest_dir: str) -> None:
    """Shallow-clone a repo with token auth into dest_dir."""
    auth_url = _inject_token_into_url(repo_url, token)
    await _run_git(
        "clone",
        "--depth",
        "1",
        "--branch",
        branch,
        auth_url,
        ".",
        cwd=dest_dir,
    )
    logger.info("repo_cloned", repo_url=repo_url, branch=branch)


async def create_branch(repo_dir: str, branch_name: str) -> None:
    """Create and checkout a new branch."""
    await _run_git("checkout", "-b", branch_name, cwd=repo_dir)


async def has_changes(repo_dir: str) -> bool:
    """Return True if the working tree has uncommitted changes."""
    output = await _run_git("status", "--porcelain", cwd=repo_dir)
    return len(output) > 0


async def commit_and_push(
    repo_dir: str,
    branch_name: str,
    commit_message: str,
    token: str,
    repo_url: str,
) -> None:
    """Stage all changes, commit, and push to remote."""
    await _run_git("add", "-A", cwd=repo_dir)
    await _run_git(
        "commit",
        "-m",
        commit_message,
        "--author",
        "Oopsie Bot <oopsie@noreply.github.com>",
        cwd=repo_dir,
    )
    auth_url = _inject_token_into_url(repo_url, token)
    await _run_git("push", auth_url, branch_name, cwd=repo_dir)
    logger.info("changes_pushed", branch=branch_name)


async def create_pull_request(
    repo_owner: str,
    repo_name: str,
    token: str,
    head_branch: str,
    base_branch: str,
    title: str,
    body: str,
) -> str:
    """Create a GitHub pull request via REST API. Returns the PR URL."""
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/pulls"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            json={
                "title": title,
                "body": body,
                "head": head_branch,
                "base": base_branch,
            },
        )
    if resp.status_code not in (200, 201):
        raise GitHubApiError(f"PR creation failed ({resp.status_code}): {resp.text}")
    pr_url: str = resp.json()["html_url"]
    logger.info("pull_request_created", pr_url=pr_url)
    return pr_url


def parse_repo_owner_name(github_repo_url: str) -> tuple[str, str]:
    """Extract (owner, name) from a GitHub URL.

    Handles HTTPS URLs like:
      https://github.com/owner/repo
      https://github.com/owner/repo.git
    """
    parsed = urlparse(github_repo_url)
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) < 2:
        raise ValueError(f"Cannot parse owner/name from URL: {github_repo_url}")
    return parts[0], parts[1]
