import os
from typing import Any, Dict, List, Optional

from google.adk.agents import Agent

# Import Jira tool adapter
from tools.jira_tool import JiraTool

def _get_tool() -> JiraTool:
    """Create a JiraTool instance on demand using env vars.
    This avoids import-time failures if credentials are not set yet.
    """
    return JiraTool(
        jira_url=os.getenv("JIRA_URL"),
        username=os.getenv("JIRA_USERNAME"),
        api_token=os.getenv("JIRA_API_TOKEN"),
    )


# Expose plain callables for ADK to register as tools. Each resolves the tool lazily.

def get_issue(issue_key: str) -> Dict[str, Any]:
    """Fetch a Jira issue by key (e.g., "PROJ-123")."""
    return _get_tool().get_issue(issue_key)


def get_all_boards() -> Optional[List[Dict[str, Any]]]:
    """List all Jira boards."""
    return _get_tool().get_all_boards()


def get_active_sprints(board_id: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
    """List active sprints for a board. If board_id is not provided, uses the first board."""
    return _get_tool().get_active_sprints(board_id)


# Define the root agent that the Dev UI will discover
root_agent = Agent(
    name="jira_agent",
    model="gemini-2.0-flash",
    description="Agent to query Jira issues, boards and active sprints.",
    instruction=(
        "You are a helpful agent that can query Jira issues, boards and active sprints using the provided tools."
    ),
    tools=[get_issue, get_all_boards, get_active_sprints],
)
