import os
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools import FunctionTool
from .sub_agents.jira_agent.agent import get_current_sprint

load_dotenv()

root_agent = Agent(
    name="core",
    model="gemini-2.0-flash",
    description="cordinates between all sub-agents to complete user tasks.",
    instruction="""
You are the core agent of a multi-agent system designed to manage and complete user tasks efficiently. 
Your primary role is to coordinate between various specialized sub-agents, delegating tasks based on their expertise and capabilities.
When using the 'get_current_sprint' tool, you must ask the user for the 'project_key' as it is a required argument for that tool.
    """,
    sub_agents=[],
    tools=[
        FunctionTool(get_current_sprint),
    ]
)