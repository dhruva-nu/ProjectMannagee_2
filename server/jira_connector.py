
import requests

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

# Example Usage (replace with your actual Jira details)
if __name__ == "__main__":
    JIRA_URL = "https://your-jira-instance.atlassian.net"  # e.g., "https://your-company.atlassian.net"
    JIRA_USERNAME = "your-email@example.com"
    JIRA_API_TOKEN = "YOUR_API_TOKEN"  # Generate this from your Atlassian account settings

    connector = JiraConnector(JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN)

    # Example: Get an issue
    issue_data = connector.get_issue("YOUR_ISSUE_KEY")  # e.g., "PROJ-123"

    if issue_data:
        print(f"Successfully fetched issue: {issue_data.get('key')}")
        print(f"Summary: {issue_data.get('fields', {}).get('summary')}")
    else:
        print("Failed to fetch issue.")


# To run this code, you need to install the 'requests' library:
# pip install requests
