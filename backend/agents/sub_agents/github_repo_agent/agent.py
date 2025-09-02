from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from backend.tools.github.repo_tools import list_repositories

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
