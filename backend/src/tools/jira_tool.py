import os
from typing import Any, Dict, List, Optional

from connectors.jira_connector import JiraConnector


class JiraTool:
    """
    Thin adapter to expose Jira actions for an Agent Dev Kit tool interface.

    Exposed actions:
    - get_issue(issue_key: str) -> dict
    - get_all_boards() -> list[dict]
    - get_active_sprints(board_id: Optional[int]) -> list[dict]
    """

    def __init__(self, jira_url: Optional[str] = None, username: Optional[str] = None, api_token: Optional[str] = None):
        self.jira_url = jira_url or os.getenv("JIRA_URL")
        self.username = username or os.getenv("JIRA_USERNAME")
        self.api_token = api_token or os.getenv("JIRA_API_TOKEN")

        if not all([self.jira_url, self.username, self.api_token]):
            missing = [
                name for name, val in (
                    ("JIRA_URL", self.jira_url), ("JIRA_USERNAME", self.username), ("JIRA_API_TOKEN", self.api_token)
                ) if not val
            ]
            raise ValueError(
                f"Missing required Jira credentials: {', '.join(missing)}.\n"
                "Set them in environment variables or pass explicitly to JiraTool(...)."
            )

        self.connector = JiraConnector(self.jira_url, self.username, self.api_token)

    # ---- Actions ----
    def get_issue(self, issue_key: str) -> Dict[str, Any]:
        return self.connector.get_issue(issue_key)

    def get_all_boards(self) -> Optional[List[Dict[str, Any]]]:
        return self.connector.get_all_boards()

    def get_active_sprints(self, board_id: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
        return self.connector.get_active_sprints(board_id)


# Optional: tool spec helpers commonly used by ADKs to auto-register tools & actions

def tool_name() -> str:
    return "jira"


def tool_description() -> str:
    return "Interact with Jira to fetch issues, boards, and active sprints. Requires JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN."


def tool_actions_schema() -> Dict[str, Any]:
    """
    JSON-like schema describing the actions and parameters. This pattern is recognized by many ADKs.
    """
    return {
        "get_issue": {
            "description": "Fetch a Jira issue by key (e.g., 'PROJ-123').",
            "parameters": {
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Jira issue key"}
                },
                "required": ["issue_key"],
            },
        },
        "get_all_boards": {
            "description": "List all Jira boards.",
            "parameters": {"type": "object", "properties": {}},
        },
        "get_active_sprints": {
            "description": "List active sprints for a board. If board_id is not provided, uses the first board.",
            "parameters": {
                "type": "object",
                "properties": {
                    "board_id": {"type": "integer", "nullable": True, "description": "Jira board ID"}
                },
            },
        },
    }


def instantiate_tool() -> JiraTool:
    """Factory used by some ADKs for discovery-based loading"""
    return JiraTool()
