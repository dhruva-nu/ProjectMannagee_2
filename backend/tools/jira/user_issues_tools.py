import os
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth

def _jira_env():
    jira_server = os.getenv("JIRA_SERVER")
    jira_username = os.getenv("JIRA_USERNAME")
    jira_api_token = os.getenv("JIRA_API")
    if not all([jira_server, jira_username, jira_api_token]):
        raise ValueError(
            "Error: Jira environment variables (JIRA_SERVER, JIRA_USERNAME, JIRA_API) are not set."
        )
    return jira_server, jira_username, jira_api_token

def get_issues_assigned_to_user(username: str) -> dict:
    """
    Fetches all Jira issues assigned to a specific user and returns raw data.

    Args:
        username: The username (display name or account ID) of the assignee.

    Returns:
        Raw data containing the assigned Jira issues.
    """
    load_dotenv()
    jira_server, jira_username, jira_api_token = _jira_env()
    auth = HTTPBasicAuth(jira_username, jira_api_token)
    headers = {"Accept": "application/json"}

    jql_query = f'assignee = "{username}" ORDER BY created DESC'
    search_url = f"{jira_server}/rest/api/2/search"

    all_issues = []
    start_at = 0
    max_results = 50

    while True:
        params = {
            "jql": jql_query,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": "key,summary,status,priority,assignee"
        }
        response = requests.get(search_url, headers=headers, auth=auth, params=params).json()

        if response.get("errorMessages"):
            return {"error": f"Error fetching issues: {response.get('errorMessages')}"}

        issues = response.get("issues", [])
        if not issues:
            break

        for issue in issues:
            fields = issue.get("fields", {})
            all_issues.append({
                "key": issue.get("key"),
                "summary": fields.get("summary"),
                "status": fields.get("status", {}).get("name"),
                "priority": fields.get("priority", {}).get("name"),
                "url": f"{jira_server}/browse/{issue.get('key')}",
            })
        
        start_at += len(issues)
        if start_at >= response.get("total", 0):
            break

    if not all_issues:
        return {"title": f"No issues found assigned to {username}.", "issues": []}

    return {"title": f"Issues assigned to {username}", "issues": all_issues}

