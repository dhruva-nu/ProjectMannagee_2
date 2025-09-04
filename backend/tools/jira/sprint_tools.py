import os
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth
from google.adk.agents import Agent

"""
Jira Sprint tools: low-level functions and in-module memory used by the Jira sprint agent.
These functions can be wrapped via FunctionTool by an orchestrating agent.
"""

# Lightweight in-process memory
_MEMORY = {
    "project_key": None,  # type: str | None
    "sprint": None,       # type: dict | None
}

def _remember(project_key: str | None = None, sprint: dict | None = None):
    if project_key:
        _MEMORY["project_key"] = project_key
    if sprint:
        _MEMORY["sprint"] = sprint

def _recall_project_key() -> str | None:
    return _MEMORY.get("project_key")

def _recall_active_sprint() -> dict | None:
    return _MEMORY.get("sprint")

def _fetch_active_sprint(project_key: str) -> dict | None:
    """Fetch the first active sprint for the project and remember it."""
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
        sprint_info = {
            "id": active["id"],
            "name": active["name"],
            "startDate": active.get("startDate"),
            "endDate": active.get("endDate"),
        }
        _remember(project_key=project_key, sprint=sprint_info)
        return sprint_info
    return None

def _fetch_issues_in_active_sprint(project_key: str, max_results: int = 50):
    """Fetch simplified issues for the active sprint."""
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

# Public tools

def summarize_current_sprint_default() -> str:
    """No-arg tool: uses remembered project_key if available."""
    project_key = _recall_project_key()
    if not project_key:
        return "Please provide a Jira project_key."
    return summarize_current_sprint_v1(project_key)

def summarize_issues_in_sprint_default(max_results: int = 50) -> str:
    """No-arg tool: uses remembered project_key if available."""
    project_key = _recall_project_key()
    if not project_key:
        return "Please provide a Jira project_key."
    return summarize_issues_in_sprint_v1(project_key, max_results=max_results)

def summarize_current_sprint_v1(project_key: str) -> str:
    """
    Summarize the current active sprint for the provided Jira project.
    Uses an LLM if available via the ADK Agent, falling back to deterministic summary.
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
            name="jira_sprint_llm",
            model="gemini-2.0-flash",
            description="Summarizes Jira sprint details",
            instruction=system_instruction,
            tools=[],
            sub_agents=[],
        )
        run_fn = getattr(llm_agent, "run", None)
        if callable(run_fn):
            answer = run_fn(user_prompt)
            return answer["text"] if isinstance(answer, dict) and "text" in answer else str(answer)
        # Fallback deterministic summary
        name = sprint.get("name")
        start = sprint.get("startDate")
        end = sprint.get("endDate")
        return f"Active sprint: {name}. Start: {start}, End: {end}."
    except Exception as e:
        name = sprint.get("name")
        start = sprint.get("startDate")
        end = sprint.get("endDate")
        return f"Active sprint: {name}. Start: {start}, End: {end}. (LLM fallback due to error: {e})"

def summarize_issues_in_sprint_v1(project_key: str, max_results: int = 50) -> str:
    """
    Summarize issues in the current sprint for a project. Uses LLM when available, else deterministic roll-up.
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
    context = {
        "sprint": sprint,
        "issues": issues[:200],
        "issue_count": len(issues),
    }
    user_prompt = (
        "Provide a brief summary of the current sprint and its issues. If helpful, list a few key issues.\n\n"
        f"Project: {project_key}\n\nContext (JSON):\n{context}"
    )
    try:
        llm_agent = Agent(
            name="jira_issues_llm",
            model="gemini-2.0-flash",
            description="Summarizes Jira sprint issues",
            instruction=system_instruction,
            tools=[],
            sub_agents=[],
        )
        run_fn = getattr(llm_agent, "run", None)
        if callable(run_fn):
            answer = run_fn(user_prompt)
            return answer["text"] if isinstance(answer, dict) and "text" in answer else str(answer)
        # Deterministic roll-up
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
        return "\n".join(lines)
    except Exception as e:
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

def get_issues_for_active_sprint_v1(project_key: str) -> list[dict]:
    """
    Retrieves a list of issues for the current active sprint in a given Jira project.
    Each issue is returned as a simplified dictionary containing key, summary, status, and assignee.
    """
    load_dotenv()
    data, err = _fetch_issues_in_active_sprint(project_key)
    if err:
        return [] # Return empty list on error
    if isinstance(data, str): # This case handles "No active sprint found" message
        return []
    return data.get("issues", [])

def get_issues_for_active_sprint_default() -> list[dict]:
    """
    Retrieves a list of issues for the current active sprint using the remembered project_key.
    Each issue is returned as a simplified dictionary containing key, summary, status, and assignee.
    """
    project_key = _recall_project_key()
    if not project_key:
        return [] # Return empty list if no project_key is remembered
    return get_issues_for_active_sprint_v1(project_key)
