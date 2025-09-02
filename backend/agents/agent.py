import os
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from .sub_agents.jira_agent.agent import jira_agent
from .sub_agents.github_agent.agent import github_agent
from .sub_agents.cpa_agent.agent import cpa_agent

load_dotenv()

root_agent = Agent(
    name="core",
    model="gemini-2.0-flash",
    description="cordinates between all sub-agents to complete user tasks.",
    instruction="""
You are the core agent of a multi-agent system designed to manage and complete user tasks efficiently. 
Your primary role is to coordinate between various specialized sub-agents, delegating tasks based on their expertise and capabilities.
When using the 'summarize_current_sprint' or 'summarize_issues_in_sprint' tools, you must ask the user for the 'project_key' as it is a required argument for those tools.
When using the 'list_repositories' tool, you must ask the user for the 'organization' as it is a required argument for that tool.
When using the 'answer_jira_query' tool, you must ask the user for the 'issue_key' and the 'query' (e.g., "when can i expect TESTPROJ-10 to be complete" or "why is TESTPROJ-10 stuck") as they are required arguments for that tool.
    """,
    sub_agents=[jira_agent, github_agent, cpa_agent],
    tools=[
        AgentTool(jira_agent),
        AgentTool(github_agent),
        AgentTool(cpa_agent),
    ]
)