import os
from dotenv import load_dotenv
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, List

"""
GitHub repository tools: functions that can be wrapped by an orchestrating agent.
"""

def list_repositories(organization: str) -> str:
    """
    Lists repositories for a given GitHub organization, returns the latest changed repo.
    """
    load_dotenv()

    github_token = os.getenv("GITHUB_TOKEN")

    if not github_token:
        return "Error: GitHub environment variable (GITHUB_TOKEN) is not set."

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {github_token}"
    }

    try:
        repos_url = f"https://api.github.com/orgs/{organization}/repos"
        response = requests.get(repos_url, headers=headers)
        response.raise_for_status()
        repositories = response.json()

        if repositories:
            repositories.sort(key=lambda repo: repo.get('pushed_at', ''), reverse=True)
            latest_repo = repositories[0]
            return f"Latest changed repository for {organization}: {latest_repo['name']} (Last Pushed: {latest_repo.get('pushed_at', 'N/A')})"
        else:
            return f"No repositories found for organization {organization}."

    except requests.exceptions.RequestException as e:
        return f"An error occurred: {e}"


def list_todays_commits(repo_full_name: str, branch: Optional[str] = None) -> str:
    """
    List all commits made today (local machine's timezone) for a given repository.

    Args:
        repo_full_name: The full repo name in the format "owner/repo" (e.g., "octocat/Hello-World").
        branch: Optional branch to filter on. When omitted, GitHub will use the default branch.

    Returns:
        A human-readable string listing commit SHA, author, time, and message for commits made today.
        If none found or on error, returns a concise message explaining the situation.
    """
    load_dotenv()

    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        return "Error: GitHub environment variable (GITHUB_TOKEN) is not set."

    # Determine local day's start and end, then convert to UTC ISO8601 as required by GitHub API.
    now_local = datetime.now().astimezone()
    start_of_day_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day_local = start_of_day_local + timedelta(days=1)
    since_utc = start_of_day_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    until_utc = end_of_day_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {github_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    params = {
        "since": since_utc,
        "until": until_utc,
        "per_page": 100,
    }
    if branch:
        params["sha"] = branch

    try:
        commits_url = f"https://api.github.com/repos/{repo_full_name}/commits"
        response = requests.get(commits_url, headers=headers, params=params)
        response.raise_for_status()
        commits = response.json()

        if not isinstance(commits, list):
            return "Unexpected response from GitHub when listing commits."

        if not commits:
            local_day_str = start_of_day_local.strftime("%Y-%m-%d")
            return f"No commits found for {repo_full_name} on {local_day_str}."

        lines: List[str] = []
        local_day_str = start_of_day_local.strftime("%Y-%m-%d")
        lines.append(f"Commits for {repo_full_name} on {local_day_str} (local time):")
        for c in commits:
            sha = c.get("sha", "")[:7]
            commit = c.get("commit", {})
            msg = commit.get("message", "").splitlines()[0]
            author = commit.get("author", {})
            author_name = author.get("name", "unknown")
            author_date_str = author.get("date")
            try:
                # Convert commit time (UTC ISO8601) to local time for display
                if author_date_str:
                    dt_utc = datetime.fromisoformat(author_date_str.replace("Z", "+00:00")).astimezone(timezone.utc)
                    dt_local = dt_utc.astimezone(now_local.tzinfo)
                    t_local = dt_local.strftime("%H:%M")
                else:
                    t_local = "--:--"
            except Exception:
                t_local = author_date_str or "--:--"

            lines.append(f"- {t_local} {sha} {author_name}: {msg}")

        return "\n".join(lines)

    except requests.exceptions.RequestException as e:
        return f"An error occurred while fetching commits: {e}"
