import os
from dotenv import load_dotenv
import requests

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
