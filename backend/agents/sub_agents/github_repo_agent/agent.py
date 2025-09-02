import os
from dotenv import load_dotenv
import requests
from google.adk.agents import Agent
from google.adk.tools import FunctionTool

def list_repositories(organization: str) -> str:
    """
    Lists repositories for a given GitHub organization.

    Args:
        organization (str): The name of the GitHub organization.

    Returns:
        str: A formatted string of repository names, or an error message.
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
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        repositories = response.json()

        if repositories:
            # Sort repositories by 'pushed_at' in descending order to get the latest changed
            repositories.sort(key=lambda repo: repo.get('pushed_at', ''), reverse=True)
            latest_repo = repositories[0]
            return f"Latest changed repository for {organization}: {latest_repo['name']} (Last Pushed: {latest_repo.get('pushed_at', 'N/A')})"
        else:
            return f"No repositories found for organization {organization}."

    except requests.exceptions.RequestException as e:
        return f"An error occurred: {e}"

# Expose as a sub-agent that can be used via AgentTool by the root agent
github_repo_agent = Agent(
    name="github_repo_agent",
    model="gemini-2.0-flash",
    description="GitHub sub-agent that lists repositories and related metadata",
    instruction=(
        "You are a GitHub sub-agent. Use your tools to list repositories for an organization. "
        "Ask for required parameter: 'organization'."
    ),
    tools=[
        FunctionTool(list_repositories),
    ],
    sub_agents=[],
)
