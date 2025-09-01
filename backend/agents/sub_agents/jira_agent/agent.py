import os
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth

def get_current_sprint(project_key: str) -> dict:
    """
    Retrieves the current active sprint for a given Jira project.

    Args:
        project_key (str): The key of the Jira project (e.g., "PROJ").

    Returns:
        dict: Sprint metadata {id, name, startDate, endDate}, or None if none is found.
    """
    load_dotenv()

    jira_server = os.getenv("JIRA_SERVER")
    jira_username = os.getenv("JIRA_USERNAME")
    jira_api_token = os.getenv("JIRA_API")

    if not all([jira_server, jira_username, jira_api_token]):
        raise ValueError("Error: Jira environment variables (JIRA_SERVER, JIRA_USERNAME, JIRA_API) are not set.")

    auth = HTTPBasicAuth(jira_username, jira_api_token)
    headers = {"Accept": "application/json"}

    # 1. Get boards for the project
    boards_url = f"{jira_server}/rest/agile/1.0/board?projectKeyOrId={project_key}"
    boards = requests.get(boards_url, headers=headers, auth=auth).json()

    if not boards.get("values"):
        return None

    board_id = boards["values"][0]["id"]  # pick the first board (or allow user choice)

    # 2. Get active sprints for that board
    sprints_url = f"{jira_server}/rest/agile/1.0/board/{board_id}/sprint?state=active"
    sprints = requests.get(sprints_url, headers=headers, auth=auth).json()

    if sprints.get("values"):
        active = sprints["values"][0]
        return {
            "id": active["id"],
            "name": active["name"],
            "startDate": active.get("startDate"),
            "endDate": active.get("endDate"),
        }
    else:
        return None


def get_issues_in_sprint(project_key: str, max_results: int = 50):
    """
    Fetches all issues in the current active sprint for a Jira project (with pagination).

    Args:
        project_key (str): The key of the Jira project (e.g., "PROJ").
        max_results (int): Max results per request (default=50).

    Returns:
        dict: { sprint: {...}, issues: [...] }
    """
    load_dotenv()

    jira_server = os.getenv("JIRA_SERVER")
    jira_username = os.getenv("JIRA_USERNAME")
    jira_api_token = os.getenv("JIRA_API")

    if not all([jira_server, jira_username, jira_api_token]):
        raise ValueError("Error: Jira environment variables (JIRA_SERVER, JIRA_USERNAME, JIRA_API) are not set.")

    auth = HTTPBasicAuth(jira_username, jira_api_token)
    headers = {"Accept": "application/json"}

    sprint = get_current_sprint(project_key)
    if not sprint:
        return f"No active sprint found for project {project_key}"

    sprint_id = sprint["id"]
    issues_url = f"{jira_server}/rest/agile/1.0/sprint/{sprint_id}/issue"

    all_issues = []
    start_at = 0

    while True:
        params = {"startAt": start_at, "maxResults": max_results}
        response = requests.get(issues_url, headers=headers, auth=auth, params=params).json()

        issues = response.get("issues", [])
        all_issues.extend(issues)

        if start_at + max_results >= response.get("total", 0):
            break

        start_at += max_results

    result = []
    for issue in all_issues:
        fields = issue.get("fields", {})
        result.append({
            "key": issue["key"],
            "summary": fields.get("summary"),
            "status": fields.get("status", {}).get("name"),
            "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
        })

    return {
        "sprint": sprint,
        "issues": result,
    }

def get_issue_details(issue_key: str) -> dict:
    """
    Retrieves detailed information for a specific Jira issue.

    Args:
        issue_key (str): The key of the Jira issue (e.g., "TESTPROJ-10").

    Returns:
        dict: Detailed issue information, or None if the issue is not found.
    """
    load_dotenv()

    jira_server = os.getenv("JIRA_SERVER")
    jira_username = os.getenv("JIRA_USERNAME")
    jira_api_token = os.getenv("JIRA_API")

    if not all([jira_server, jira_username, jira_api_token]):
        raise ValueError("Error: Jira environment variables (JIRA_SERVER, JIRA_USERNAME, JIRA_API) are not set.")

    auth = HTTPBasicAuth(jira_username, jira_api_token)
    headers = {"Accept": "application/json"}

    issue_url = f"{jira_server}/rest/api/2/issue/{issue_key}"
    response = requests.get(issue_url, headers=headers, auth=auth).json()

    if response.get("errorMessages") or response.get("errors"):
        print(f"Error fetching issue {issue_key}: {response.get('errorMessages', response.get('errors'))}")
        return None

    fields = response.get("fields", {})
    return {
        "key": response.get("key"),
        "summary": fields.get("summary"),
        "status": fields.get("status", {}).get("name"),
        "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
        "reporter": fields.get("reporter", {}).get("displayName") if fields.get("reporter") else None,
        "priority": fields.get("priority", {}).get("name"),
        "issue_type": fields.get("issuetype", {}).get("name"),
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "duedate": fields.get("duedate"),
        "resolutiondate": fields.get("resolutiondate"),
        "description": fields.get("description"),
        "comments": [comment.get("body") for comment in fields.get("comment", {}).get("comments", [])],
        "labels": fields.get("labels", []),
        "components": [comp.get("name") for comp in fields.get("components", [])],
        "fix_versions": [fv.get("name") for fv in fields.get("fixVersions", [])],
        "custom_fields": {k: v for k, v in fields.items() if k.startswith('customfield_')}
    }
