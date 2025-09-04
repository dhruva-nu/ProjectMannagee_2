from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from tools.github.repo_tools import list_repositories, list_todays_commits

# Expose as a sub-agent that can be used via AgentTool by the root agent
github_repo_agent = Agent(
    name="github_repo_agent",
    model="gemini-2.0-flash",
    description="GitHub sub-agent that lists repositories and related metadata",
    instruction=(
        "You are a GitHub sub-agent. Use your tools to: "
        "1) list repositories for an organization (requires 'organization'), and "
        "2) list all commits made today for a repository (requires 'repo_full_name' like 'owner/repo', optional 'branch')."
    ),
    tools=[
        FunctionTool(list_repositories),
        FunctionTool(list_todays_commits),
    ],
    sub_agents=[],
)
