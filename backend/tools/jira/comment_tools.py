import os
from typing import Dict, Any
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth


def _jira_env():
    """
    Reads required Jira environment variables and validates presence.

    Required:
    - JIRA_SERVER
    - JIRA_USERNAME
    - JIRA_API (API token)
    """
    jira_server = os.getenv("JIRA_SERVER")
    jira_username = os.getenv("JIRA_USERNAME")
    jira_api_token = os.getenv("JIRA_API")
    if not all([jira_server, jira_username, jira_api_token]):
        raise ValueError(
            "Error: Jira environment variables (JIRA_SERVER, JIRA_USERNAME, JIRA_API) are not set."
        )
    return jira_server.rstrip("/"), jira_username, jira_api_token


def add_comment_to_jira_issue(issue_key: str, comment_body: str) -> Dict[str, Any]:
    """
    Add a comment to a Jira issue.

    Args:
        issue_key: The Jira issue key (e.g., "TESTPROJ-26").
        comment_body: The text of the comment to add.

    Returns:
        Dict with either a success payload containing comment details or an error.
    """
    load_dotenv()

    if not issue_key or not isinstance(issue_key, str):
        return {"error": "Invalid or missing issue_key"}
    if not comment_body or not isinstance(comment_body, str):
        return {"error": "Invalid or missing comment_body"}

    jira_server, jira_username, jira_api_token = _jira_env()
    auth = HTTPBasicAuth(jira_username, jira_api_token)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    url = f"{jira_server}/rest/api/2/issue/{issue_key}/comment"
    payload = {"body": comment_body}

    try:
        resp = requests.post(url, json=payload, headers=headers, auth=auth)
        # Try to parse JSON regardless; if not JSON, requests will raise on .json() call
        data = resp.json() if resp.content else {}
    except Exception as e:
        return {"error": f"Failed to add comment: {e}"}

    if resp.status_code not in (200, 201):
        # Standard Jira error format often includes errorMessages
        err = data.get("errorMessages") or data.get("errors") or data
        return {"error": f"Jira API error (status {resp.status_code})", "details": err}

    # Success: Jira returns the created comment representation
    comment_id = data.get("id")
    comment_url = f"{jira_server}/browse/{issue_key}?focusedCommentId={comment_id}" if comment_id else f"{jira_server}/browse/{issue_key}"
    return {
        "success": True,
        "issue_key": issue_key,
        "comment_id": comment_id,
        "comment_body": data.get("body", comment_body),
        "self": data.get("self"),
        "url": comment_url,
    }
