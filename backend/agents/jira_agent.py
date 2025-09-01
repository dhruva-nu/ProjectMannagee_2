import os
from jira import JIRA
from google.adk.agents import LlmAgent
from google.adk.agents.llm import Gemini
from google.adk.tools import FunctionTool

def get_latest_sprint() -> str:
    """Gets the latest sprint from Jira.

    Returns:
        The name of the latest sprint.
    """
    jira_server = os.environ.get("JIRA_SERVER")
    jira_username = os.environ.get("JIRA_USERNAME")
    jira_api_token = os.environ.get("JIRA_API_TOKEN")

    if not all([jira_server, jira_username, jira_api_token]):
        return "Jira credentials are not set. Please set the JIRA_SERVER, JIRA_USERNAME, and JIRA_API_TOKEN environment variables."

    try:
        jira = JIRA(server=jira_server, basic_auth=(jira_username, jira_api_token))
        # First, get the board
        boards = jira.boards()
        if not boards:
            return "No boards found in your Jira instance."
        # Assuming the first board is the correct one
        board_id = boards[0].id
        sprints = jira.sprints(board_id, state='active')
        if not sprints:
            return "No active sprints found."
        latest_sprint = sprints[-1]
        return latest_sprint.name
    except Exception as e:
        return f"An error occurred: {e}"

jira_tool = FunctionTool(get_latest_sprint)
jira_agent = LlmAgent(
    llm=Gemini(),
    tools=[jira_tool],
)

if __name__ == "__main__":
    while True:
        print(jira_agent.chat(input("You: ")))