from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from .tools.formatting_tools import (
    format_jira_status,
    format_issue_list,
    format_user_card,
    format_assignee_response,
    format_eta_response,
    format_cpa_summary,
    format_sprint_summary,
    format_issue_details,
    format_dependency_graph,
    format_error_response,
    format_generic_response
)

"""
This module defines `formatter_agent`, a specialized Agent responsible for 
formatting all output responses from other agents into consistent UI-ready formats.
This centralizes all formatting logic and removes formatting responsibilities from other agents.
"""

formatter_agent = Agent(
    name="formatter_agent",
    model="gemini-2.0-flash",
    description="Formatting agent that converts raw data from other agents into structured UI-ready formats",
    instruction=(
        "You are a specialized formatting agent responsible for converting raw data "
        "from other agents into structured, UI-ready formats. Your role is to:\n"
        "1. Take raw data and user context as input\n"
        "2. Apply appropriate formatting based on the data type and user intent\n"
        "3. Return consistently structured JSON responses for the frontend\n"
        "4. Handle error cases with appropriate error formatting\n"
        "5. Ensure all responses follow the established UI directive patterns\n\n"
        "Available formatting types:\n"
        "- jira_status: For Jira issue status queries\n"
        "- issue_list: For lists of Jira issues\n"
        "- user_card: For user information display\n"
        "- assignee_response: For assignee lookup results\n"
        "- eta_response: For ETA/timeline estimates\n"
        "- cpa_summary: For Critical Path Analysis summaries\n"
        "- sprint_summary: For sprint overview data\n"
        "- issue_details: For detailed issue information\n"
        "- dependency_graph: For issue dependency visualizations\n"
        "- error_response: For error handling\n"
        "- generic_response: For general data formatting\n\n"
        "Always choose the most appropriate formatting function based on the data type and user intent."
    ),
    tools=[
        FunctionTool(format_jira_status),
        FunctionTool(format_issue_list),
        FunctionTool(format_user_card),
        FunctionTool(format_assignee_response),
        FunctionTool(format_eta_response),
        FunctionTool(format_cpa_summary),
        FunctionTool(format_sprint_summary),
        FunctionTool(format_issue_details),
        FunctionTool(format_dependency_graph),
        FunctionTool(format_error_response),
        FunctionTool(format_generic_response),
    ],
    sub_agents=[],
)
