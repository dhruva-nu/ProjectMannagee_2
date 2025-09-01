import os
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth

def get_current_sprint(project_key: str) -> str:
    """
    Retrieves the current active sprint for a given Jira project.

    Args:
        project_key (str): The key of the Jira project (e.g., "PROJ").

    Returns:
        str: The name of the current active sprint, or a message if none is found.
    """

    load_dotenv()

    jira_server = os.getenv("JIRA_SERVER")
    jira_username = os.getenv("JIRA_USERNAME")
    jira_api_token = os.getenv("JIRA_API")

    if not all([jira_server, jira_username, jira_api_token]):
        return "Error: Jira environment variables (JIRA_SERVER, JIRA_USERNAME, JIRA_API_TOKEN) are not set."

    auth = HTTPBasicAuth(jira_username, jira_api_token)
    headers = {"Accept": "application/json"}

    try:
        # 1. Get boards for the project
        boards_url = f"{jira_server}/rest/agile/1.0/board?projectKeyOrId={project_key}"
        boards = requests.get(boards_url, headers=headers, auth=auth).json()

        if not boards.get("values"):
            return f"No boards found for project {project_key}"

        board_id = boards["values"][0]["id"]  # pick the first board (or let user choose)

        # 2. Get active sprints for that board
        sprints_url = f"{jira_server}/rest/agile/1.0/board/{board_id}/sprint?state=active"
        sprints = requests.get(sprints_url, headers=headers, auth=auth).json()

        if sprints.get("values"):
            active = sprints["values"][0]
            return (
                f"Active sprint in {project_key}: {active['name']} "
                f"(Start: {active.get('startDate')}, End: {active.get('endDate')})"
            )
        else:
            return f"No active sprint found for project {project_key}"

    except Exception as e:
        return f"An error occurred: {e}"