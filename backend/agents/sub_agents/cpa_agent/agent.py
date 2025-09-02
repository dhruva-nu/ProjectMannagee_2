import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
import requests
from requests.auth import HTTPBasicAuth

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

def _fetch_issue_details(issue_key: str) -> dict | None:
    """Internal: fetch detailed information for a specific Jira issue."""
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

def answer_jira_query(issue_key: str, query: str) -> str:
    """
    Use Gemini ADK (gemini-2.0-flash) to answer questions about a Jira issue
    using its details and optional project knowledge base as context.
    """
    load_dotenv()

    issue_details = _fetch_issue_details(issue_key)
    tech_stack_info = load_tech_stack_info()

    if not issue_details:
        return f"Could not find details for Jira issue {issue_key}. Please check the issue key."

    # Prepare concise, structured context for the LLM
    status = issue_details.get("status", "Unknown")
    summary = issue_details.get("summary", "No summary available")
    assignee = issue_details.get("assignee", "unassigned")
    due_date = issue_details.get("duedate")
    resolution_date = issue_details.get("resolutiondate")
    labels = issue_details.get("labels", [])
    comments = issue_details.get("comments", [])

    last_comments = comments[-3:] if comments else []
    tech_notes = tech_stack_info.get("cpa_relevant_info", {}) if tech_stack_info else {}

    system_instruction = (
        "You are a concise Jira assistant. Answer the user's question using only the provided context. "
        "Be specific, avoid hallucinations, and state uncertainties if data is missing."
    )

    context_blob = {
        "issue_key": issue_key,
        "summary": summary,
        "status": status,
        "assignee": assignee,
        "due_date": due_date,
        "resolution_date": resolution_date,
        "labels": labels,
        "last_comments": last_comments,
        "tech_notes": tech_notes,
    }

    user_prompt = (
        "Answer the user's question about this Jira issue.\n\n"
        f"Question: {query}\n\n"
        "Context (JSON):\n" + json.dumps(context_blob, ensure_ascii=False, indent=2)
    )

    try:
        llm_agent = Agent(
            name="cpa-llm",
            model="gemini-2.0-flash",
            description="CPA assistant for Jira queries",
            instruction=system_instruction,
            tools=[],
            sub_agents=[],
        )
        answer = llm_agent.run(user_prompt)
        # Some ADK versions return dict/messages; ensure we return string
        if isinstance(answer, dict) and "text" in answer:
            return answer["text"]
        return str(answer)
    except Exception as e:
        # Fallback to a simple deterministic summary if LLM fails
        fallback = [
            f"Regarding Jira issue {issue_key} ('{summary}'), currently assigned to {assignee} and in status '{status}':",
        ]
        if resolution_date:
            fallback.append(f"Resolved on {resolution_date}.")
        elif due_date:
            fallback.append(f"Due date: {due_date}.")
        if labels:
            fallback.append(f"Labels: {', '.join(labels)}.")
        if last_comments:
            fallback.append("Recent comments:")
            for i, c in enumerate(last_comments, 1):
                fallback.append(f"- {i}. {c}")
        fallback.append(f"(LLM fallback due to error: {e})")
        return "\n".join(fallback)

# Expose as a sub-agent that can be used via AgentTool by the root agent
cpa_agent = Agent(
    name="cpa_agent",
    model="gemini-2.0-flash",
    description="CPA sub-agent for answering Jira issue queries using context and project knowledge",
    instruction=(
        "You are a CPA sub-agent focused on answering questions about Jira issues. "
        "Ask for required parameters: 'issue_key' and 'query'."
    ),
    tools=[
        FunctionTool(answer_jira_query),
    ],
    sub_agents=[],
)
