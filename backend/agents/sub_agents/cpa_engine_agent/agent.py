def estimate_issue_eta_wrapper(issue_key: str, project_key: str = "") -> dict:
    """Convenience wrapper to estimate an issue's completion in the current sprint.
    If project_key is not provided, infer it from prefix of the issue key up to the first '-'.
    """
    if (not project_key) and issue_key and '-' in issue_key:
        project_key = issue_key.split('-', 1)[0]
    if not project_key:
        return {"error": "project_key required or inferable from issue_key"}
    return estimate_issue_completion_in_current_sprint(project_key=project_key, issue_key=issue_key)
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools import FunctionTool

try:
    from tools.cpa.engine_tools import (
        refresh_from_jira,
        run_cpa,
        get_critical_path,
        get_task_slack,
        get_project_duration,
        summarize_current_sprint_cpa,
        current_sprint_cpa_timeline,
        estimate_issue_completion_in_current_sprint,
        compute_eta_range_for_issue_current_sprint,
    )
except ModuleNotFoundError:
    from backend.tools.cpa.engine_tools import (
        refresh_from_jira,
        run_cpa,
        get_critical_path,
        get_task_slack,
        get_project_duration,
        summarize_current_sprint_cpa,
        current_sprint_cpa_timeline,
        estimate_issue_completion_in_current_sprint,
        compute_eta_range_for_issue_current_sprint,
    )

load_dotenv()

def estimate_issue_eta_days(issue_key: str) -> dict:
    """Return optimistic/pessimistic ETA (in days) for an issue in current sprint.
    Infers project_key from issue key prefix.
    """
    if not issue_key or '-' not in issue_key:
        return {"error": "issue_key must look like 'PROJ-123'"}
    project_key = issue_key.split('-', 1)[0]
    return compute_eta_range_for_issue_current_sprint(project_key=project_key, issue_key=issue_key)

cpa_engine_agent = Agent(
    name="cpa_engine_agent",
    model="gemini-2.0-flash",
    description=(
        "CPA Engine Agent: syncs Jira to DB and runs Critical Path Analysis over tasks/dependencies."
    ),
    instruction=(
        "You expose deterministic tools for CPA. Always return concise structured JSON from tools."
    ),
    tools=[
        FunctionTool(refresh_from_jira),
        FunctionTool(run_cpa),
        FunctionTool(get_critical_path),
        FunctionTool(get_task_slack),
        FunctionTool(get_project_duration),
        FunctionTool(summarize_current_sprint_cpa),
        FunctionTool(current_sprint_cpa_timeline),
        FunctionTool(estimate_issue_completion_in_current_sprint),
        FunctionTool(estimate_issue_eta_wrapper),
        FunctionTool(estimate_issue_eta_days),
    ],
    sub_agents=[],
)
