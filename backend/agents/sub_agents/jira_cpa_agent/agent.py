
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
try:
    from tools.jira.cpa_tools import (
        answer_jira_query,
        what_is_blocking,
        answer_sprint_hypothetical,
        who_is_assigned,
        transition_issue_status,
        add_comment_to_issue,
        print_issue_dependency_graph,
    )
except ModuleNotFoundError:
    from backend.tools.jira.cpa_tools import (
        answer_jira_query,
        what_is_blocking,
        answer_sprint_hypothetical,
        who_is_assigned,
        transition_issue_status,
        add_comment_to_issue,
        print_issue_dependency_graph,
    )

"""
This module defines `jira_cpa_agent`, an orchestrating Agent that wraps
deterministic Jira CPA tools implemented in `backend.tools.jira.cpa_tools`.
"""

# Instantiate the CPA agent after all tools are defined
jira_cpa_agent = Agent(
    name="jira_cpa_agent",
    model="gemini-2.0-flash",
    description="CPA sub-agent for answering Jira issue and sprint planning queries using context and project knowledge",
    instruction=(
        "You are a CPA sub-agent focused on Jira issue analysis and sprint planning.\n"
        "- For blockers, you MUST call what_is_blocking(issue_key) and return ONLY the tool output.\n"
        "- For assignee queries (e.g., 'who is assigned ISSUE-123'), you MUST call who_is_assigned(issue_key) and return ONLY the tool's JSON output, no prose. Do NOT answer in free text.\n"
        "- For generic issue Q&A, call answer_jira_query(issue_key, query).\n"
        "- For hypothetical sprint planning (e.g., moving an issue and projecting completion), call "
        "answer_sprint_hypothetical(project_key, issue_key, query). Ask for any missing required parameters."
    ),
    tools=[
        FunctionTool(answer_jira_query),
        FunctionTool(what_is_blocking),
        FunctionTool(answer_sprint_hypothetical),
        FunctionTool(who_is_assigned),
        FunctionTool(transition_issue_status),
        FunctionTool(add_comment_to_issue),
        FunctionTool(print_issue_dependency_graph),
    ],
    sub_agents=[],
)
