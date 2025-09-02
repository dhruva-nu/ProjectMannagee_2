import os
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth
from google.adk.agents import Agent
from google.adk.tools import FunctionTool

def _fetch_active_sprint(project_key: str) -> dict | None:
    """Internal: fetch the first active sprint for the project."""
    jira_server = os.getenv("JIRA_SERVER")
    jira_username = os.getenv("JIRA_USERNAME")
    jira_api_token = os.getenv("JIRA_API")
    if not all([jira_server, jira_username, jira_api_token]):
        raise ValueError("Error: Jira environment variables (JIRA_SERVER, JIRA_USERNAME, JIRA_API) are not set.")
    auth = HTTPBasicAuth(jira_username, jira_api_token)
    headers = {"Accept": "application/json"}
    boards_url = f"{jira_server}/rest/agile/1.0/board?projectKeyOrId={project_key}"
    boards = requests.get(boards_url, headers=headers, auth=auth).json()
    if not boards.get("values"):
        return None
    board_id = boards["values"][0]["id"]
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
    return None


def _fetch_issues_in_active_sprint(project_key: str, max_results: int = 50):
    """Internal: fetch simplified issues for the active sprint."""
    jira_server = os.getenv("JIRA_SERVER")
    jira_username = os.getenv("JIRA_USERNAME")
    jira_api_token = os.getenv("JIRA_API")
    if not all([jira_server, jira_username, jira_api_token]):
        raise ValueError("Error: Jira environment variables (JIRA_SERVER, JIRA_USERNAME, JIRA_API) are not set.")
    auth = HTTPBasicAuth(jira_username, jira_api_token)
    headers = {"Accept": "application/json"}
    sprint = _fetch_active_sprint(project_key)
    if not sprint:
        return f"No active sprint found for project {project_key}", None
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
    simplified = []
    for issue in all_issues:
        fields = issue.get("fields", {})
        simplified.append({
            "key": issue.get("key"),
            "summary": fields.get("summary"),
            "status": fields.get("status", {}).get("name"),
            "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
        })
    return {"sprint": sprint, "issues": simplified}, None

# Removed external get_issue_details; CPA agent now fetches details directly.


def summarize_current_sprint(project_key: str) -> str:
    """
    Uses Gemini ADK (gemini-2.0-flash) to generate a concise summary of the
    current active sprint for the provided Jira project. Fetches sprint data
    internally and LLM-izes the output.
    """
    load_dotenv()
    sprint = _fetch_active_sprint(project_key)
    if not sprint:
        return f"No active sprint found for project {project_key}."

    system_instruction = (
        "You are a concise Jira sprint assistant. Summarize the sprint clearly "
        "using only provided context. Avoid hallucinations."
    )
    user_prompt = (
        "Summarize the active sprint for the project. Include sprint name and dates, "
        "and any notable info available.\n\nContext (JSON):\n" + str(sprint)
    )
    try:
        llm_agent = Agent(
            name="jira-sprint-llm",
            model="gemini-2.0-flash",
            description="Summarizes Jira sprint details",
            instruction=system_instruction,
            tools=[],
            sub_agents=[],
        )
        answer = llm_agent.run(user_prompt)
        return answer["text"] if isinstance(answer, dict) and "text" in answer else str(answer)
    except Exception as e:
        # Fallback to deterministic formatting
        name = sprint.get("name")
        start = sprint.get("startDate")
        end = sprint.get("endDate")
        return f"Active sprint: {name}. Start: {start}, End: {end}. (LLM fallback due to error: {e})"


def summarize_issues_in_sprint(project_key: str, max_results: int = 50) -> str:
    """
    Uses Gemini ADK (gemini-2.0-flash) to produce a concise summary of issues
    in the current sprint for a project. Fetches issues internally and
    summarizes the results.
    """
    load_dotenv()
    data, err = _fetch_issues_in_active_sprint(project_key, max_results=max_results)
    if err:
        return err
    if isinstance(data, str):
        return data
    sprint = data.get("sprint")
    issues = data.get("issues", [])

    system_instruction = (
        "You are a concise Jira assistant. Summarize sprint issues using only the provided context. "
        "Highlight counts per status, notable assignments, and any due dates if present."
    )
    # Keep context compact; LLM can compute aggregates
    context = {
        "sprint": sprint,
        "issues": issues[:200],  # guardrail for extremely large sprints
        "issue_count": len(issues),
    }
    user_prompt = (
        "Provide a brief summary of the current sprint and its issues. If helpful, list a few key issues.\n\n"
        f"Project: {project_key}\n\nContext (JSON):\n{context}"
    )
    try:
        llm_agent = Agent(
            name="jira-issues-llm",
            model="gemini-2.0-flash",
            description="Summarizes Jira sprint issues",
            instruction=system_instruction,
            tools=[],
            sub_agents=[],
        )
        answer = llm_agent.run(user_prompt)
        return answer["text"] if isinstance(answer, dict) and "text" in answer else str(answer)
    except Exception as e:
        # Fallback: simple roll-up
        lines = []
        sprint_name = sprint.get("name") if sprint else "(unknown)"
        lines.append(f"Sprint: {sprint_name}. Issues: {len(issues)}.")
        status_counts = {}
        for it in issues:
            st = it.get("status") or "Unknown"
            status_counts[st] = status_counts.get(st, 0) + 1
        if status_counts:
            lines.append("By status: " + ", ".join(f"{k}: {v}" for k, v in status_counts.items()))
        sample = issues[:5]
        if sample:
            lines.append("Sample:")
            for it in sample:
                lines.append(f"- {it.get('key')}: {it.get('summary')} (status: {it.get('status')}, assignee: {it.get('assignee')})")
        lines.append(f"(LLM fallback due to error: {e})")
        return "\n".join(lines)

# Expose as a sub-agent that can be used via AgentTool by the root agent
# This agent provides two tools: summarize_current_sprint and summarize_issues_in_sprint
jira_agent = Agent(
    name="jira_agent",
    model="gemini-2.0-flash",
    description="Jira sub-agent handling sprint summaries and issue overviews",
    instruction=(
        "You are a specialized Jira sub-agent. Use your tools to summarize the current sprint "
        "or summarize issues in the active sprint. For summarize_current_sprint and "
        "summarize_issues_in_sprint, ask for the required 'project_key'."
    ),
    tools=[
        FunctionTool(summarize_current_sprint),
        FunctionTool(summarize_issues_in_sprint),
    ],
    sub_agents=[],
)
