
import requests
import os
from dotenv import load_dotenv

class JiraConnector:
    def __init__(self, jira_url, username, api_token):
        self.jira_url = jira_url
        self.username = username
        self.api_token = api_token
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def _get_auth(self):
        return (self.username, self.api_token)

    def get_issue(self, issue_key):
        """
        Fetches details of a specific Jira issue.
        :param issue_key: The key of the Jira issue (e.g., "PROJ-123").
        :return: A dictionary containing issue details, or None if not found/error.
        """
        url = f"{self.jira_url}/rest/api/2/issue/{issue_key}"
        try:
            response = requests.get(url, headers=self.headers, auth=self._get_auth())
            response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching issue {issue_key}: {e}")
            return None

    def get_all_boards(self):
        """
        Fetches all Jira boards.
        :return: A list of dictionaries containing board details, or None if error.
        """
        url = f"{self.jira_url}/rest/agile/1.0/board"
        try:
            response = requests.get(url, headers=self.headers, auth=self._get_auth())
            response.raise_for_status()
            return response.json().get('values')
        except requests.exceptions.RequestException as e:
            print(f"Error fetching boards: {e}")
            return None

    def get_active_sprints(self, board_id=None):
        """
        Fetches active sprints for a given board. If no board_id is provided,
        it attempts to find the first board and use its ID.
        :param board_id: The ID of the Jira board.
        :return: A list of dictionaries containing active sprint details, or None if error.
        """
        if not board_id:
            boards = self.get_all_boards()
            if boards:
                board_id = boards[0].get('id')
                print(f"No board_id provided. Using the first board found: {boards[0].get('name')} (ID: {board_id})")
            else:
                print("No boards found to retrieve active sprints.")
                return None

        url = f"{self.jira_url}/rest/agile/1.0/board/{board_id}/sprint?state=active"
        try:
            response = requests.get(url, headers=self.headers, auth=self._get_auth())
            response.raise_for_status()
            return response.json().get('values')
        except requests.exceptions.RequestException as e:
            print(f"Error fetching active sprints for board {board_id}: {e}")
            return None

# Example Usage (replace with your actual Jira details)
if __name__ == "__main__":
    load_dotenv() # Load environment variables from .env file

    JIRA_URL = os.getenv("JIRA_URL")
    JIRA_USERNAME = os.getenv("JIRA_USERNAME")
    JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

    if not all([JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN]):
        print("Error: Please set JIRA_URL, JIRA_USERNAME, and JIRA_API_TOKEN in your .env file.")
    else:
        connector = JiraConnector(JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN)

        # Example: Get an issue
        issue_data = connector.get_issue("SCRUM-1")  

        if issue_data:
            print(f"Successfully fetched issue: {issue_data.get('key')}")
            print(f"Summary: {issue_data.get('fields', {}).get('summary')}")
        else:
            print("Failed to fetch issue.")

        print("\n--- Active Sprints ---")
        active_sprints = connector.get_active_sprints()
        if active_sprints:
            for sprint in active_sprints:
                print(f"Sprint Name: {sprint.get('name')}, State: {sprint.get('state')}, ID: {sprint.get('id')}")
        else:
            print("No active sprints found.")

# To run this code, you need to install the 'requests' library:
# pip install requests
