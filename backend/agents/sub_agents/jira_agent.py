import os
from dotenv import load_dotenv
from jira import JIRA

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
    jira_api_token = os.getenv("JIRA_API_TOKEN")

    if not all([jira_server, jira_username, jira_api_token]):
        return "Error: Jira environment variables (JIRA_SERVER, JIRA_USERNAME, JIRA_API_TOKEN) are not set."

    try:
        jira = JIRA(server=jira_server, basic_auth=(jira_username, jira_api_token))

        # Search for active sprints in the specified project
        jql_query = f'project = "{project_key}" AND sprint in openSprints() ORDER BY created DESC'
        issues_in_sprint = jira.search_issues(jql_query, maxResults=1)

        if issues_in_sprint:
            # Assuming the first issue found will have the relevant sprint
            # Jira API for sprints can be a bit tricky, often linked via issues
            for field_name in issues_in_sprint[0].fields.__dict__:
                if field_name.startswith('customfield_') and 'sprint' in field_name.lower():
                    sprint_field = getattr(issues_in_sprint[0].fields, field_name)
                    if sprint_field:
                        # sprint_field is often a list of sprint objects
                        for sprint in sprint_field:
                            if hasattr(sprint, 'state') and sprint.state == 'ACTIVE':
                                return f"Current active sprint for project '{project_key}': {sprint.name}"
            return f"No active sprint found directly linked to issues in project '{project_key}'."
        else:
            return f"No issues found in an active sprint for project '{project_key}'."

    except Exception as e:
        return f"An error occurred: {e}"