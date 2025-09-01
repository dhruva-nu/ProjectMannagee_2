from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from .sub_agents.jira_agent.agent import get_current_sprint
from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool

root_agent = Agent(
    name="core",
    model="gemini-2.0-flash",
    description="cordinates between all sub-agents to complete user tasks.",
    instruction="""
You are the core agent of a multi-agent system designed to manage and complete user tasks efficiently. 
Your primary role is to coordinate between various specialized sub-agents, delegating tasks based on their expertise and capabilities.
    """,
    sub_agents=[],
    tools=[
        AgentTool(get_current_sprint),
    ]
)