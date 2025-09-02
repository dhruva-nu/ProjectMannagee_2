from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from backend.tools.cpa.engine_tools import (
    refresh_from_jira,
    run_cpa,
    get_critical_path,
    get_task_slack,
    get_project_duration,
)

load_dotenv()

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
    ],
    sub_agents=[],
)
