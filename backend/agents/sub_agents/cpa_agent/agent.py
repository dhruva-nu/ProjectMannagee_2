import json
import os
from datetime import datetime, timedelta
from ..jira_agent.agent import get_issue_details

def load_tech_stack_info():
    """Loads the tech stack information from docs/tech_stack.json."""
    try:
        with open("docs/tech_stack.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        print("Error decoding tech_stack.json. Please check its format.")
        return None

def answer_jira_query(issue_key: str, query: str) -> str:
    """
    Answers questions about Jira issue completion and status based on issue details
    and project knowledge base.

    Args:
        issue_key (str): The key of the Jira issue (e.g., "TESTPROJ-10").
        query (str): The user's query (e.g., "when can i expect TESTPROJ-10 to be complete").

    Returns:
        str: A natural language answer to the query.
    """
    issue_details = get_issue_details(issue_key)
    tech_stack_info = load_tech_stack_info()

    if not issue_details:
        return f"Could not find details for Jira issue {issue_key}. Please check the issue key."

    status = issue_details.get("status", "Unknown")
    summary = issue_details.get("summary", "No summary available")
    assignee = issue_details.get("assignee", "unassigned")
    due_date = issue_details.get("duedate")
    resolution_date = issue_details.get("resolutiondate")
    comments = issue_details.get("comments", [])
    labels = issue_details.get("labels", [])

    response = f"Regarding Jira issue {issue_key} ('{summary}'), currently assigned to {assignee} and in status '{status}':\n\n"

    query_lower = query.lower()

    if "when can i expect" in query_lower or "complete" in query_lower:
        if status in ["Done", "Closed", "Resolved"]:
            response += f"This issue is already {status}. It was resolved on {resolution_date}."
        elif due_date:
            response += f"It has a due date of {due_date}. Based on its current status '{status}', it is expected to be completed by then."
        elif status in ["To Do", "Open"]:
            response += f"This issue is currently in '{status}' status. There is no specific due date set. Completion depends on when work begins and progresses."
        elif status in ["In Progress", "In Review", "Testing"]:
            response += f"The issue is currently '{status}'. While there's no specific due date, it's actively being worked on. Progress should be monitored."
            if tech_stack_info and "scalability_strategy" in tech_stack_info.get("cpa_relevant_info", {}):
                response += f"\n\nProject's scalability strategy: {tech_stack_info['cpa_relevant_info']['scalability_strategy']}. This might influence complex task completion."
        else:
            response += f"The issue is in '{status}' status. Without a due date or further information, it's hard to predict completion. Please check with the assignee."

    if ("why is" in query_lower and "stuck" in query_lower) or "stuck" in query_lower:
        if status in ["Blocked", "On Hold", "Waiting for Information"]:
            response += f"\n\nIt appears to be stuck because its status is '{status}'. You might want to check the latest comments for reasons:"
            if comments:
                for i, comment in enumerate(comments[-2:]): # Show last 2 comments
                    response += f"\n- Comment {i+1}: {comment}"
            else:
                response += "\n- No recent comments indicate why it's stuck. Please reach out to the assignee or reporter."
        elif status in ["To Do", "Open"]:
            response += f"\n\nIt's currently in '{status}' status, meaning work hasn't started yet. It's not stuck, but awaiting prioritization or assignment."
        elif status in ["In Progress", "In Review", "Testing"]:
            response += f"\n\nIt is currently '{status}' and actively being worked on. It does not appear to be stuck."
        else:
            response += f"\n\nBased on its '{status}' status, it doesn't seem to be explicitly stuck. However, if you have concerns, check recent activity or comments."

        if "blocker" in [label.lower() for label in labels]:
            response += "\n\nAdditionally, the issue has a 'blocker' label, which indicates a significant impediment."
        if tech_stack_info and "security_audits" in tech_stack_info.get("cpa_relevant_info", {}):
            response += f"\n\nProject's security audit policy: {tech_stack_info['cpa_relevant_info']['security_audits']}. If this issue is related to security, it might be awaiting audit clearance."

    return response
