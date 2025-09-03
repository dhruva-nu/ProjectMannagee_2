jira_agent = None  # forward-declare for linting; actual instance is below
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from tools.jira.sprint_tools import (
    summarize_current_sprint_v1,
    summarize_issues_in_sprint_v1,
    summarize_current_sprint_default,
    summarize_issues_in_sprint_default,
)
from tools.jira.user_issues_tools import get_issues_assigned_to_user


"""
This module defines `jira_sprint_agent`, an orchestrating Agent that wraps
Jira sprint tools implemented in `backend.tools.jira.sprint_tools`.
"""

# Expose as a sub-agent that can be used via AgentTool by the root agent
# This agent provides two tools: summarize_current_sprint and summarize_issues_in_sprint
jira_sprint_agent = Agent(
    name="jira_sprint_agent",
    model="gemini-2.0-flash",
    description="Jira sub-agent handling sprint summaries and issue overviews",
    instruction=(
        "You are a specialized Jira sub-agent. To avoid unnecessary parameter asks: "
        "1) If the user omits project_key, prefer calling the no-arg tools that use memory: "
        "summarize_current_sprint_default and summarize_issues_in_sprint_default. "
        "2) If the user specifies project_key, call the explicit tools with that parameter: "
        "summarize_current_sprint_v1 or summarize_issues_in_sprint_v1. "
        "Only ask for project_key when neither memory nor user input provides it."
    ),
    tools=[
        FunctionTool(summarize_current_sprint_v1),
        FunctionTool(summarize_issues_in_sprint_v1),
        FunctionTool(summarize_current_sprint_default),
        FunctionTool(summarize_issues_in_sprint_default),
        FunctionTool(get_issues_assigned_to_user),
    ],
    sub_agents=[],
)
