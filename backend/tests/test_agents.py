"""
Tests for agents and sub-agents functionality.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.adk.tools.agent_tool import AgentTool

from backend.agents.agent import agent
from backend.tools.jira.cpa_tools import who_is_assigned, answer_jira_query


class TestMainAgent:
    """Test the main coordinating agent."""
    
    def test_agent_initialization(self):
        """Test that the main agent is properly initialized."""
        assert agent.name == "core"
        assert agent.model == "gemini-2.0-flash"
        assert "coordinate" in agent.description.lower()
        assert len(agent.sub_agents) > 0
        assert len(agent.tools) > 0
    
    def test_agent_has_required_tools(self):
        """Test that agent has all required tools."""
        tool_names = []
        for tool in agent.tools:
            if hasattr(tool, 'func'):
                tool_names.append(tool.func.__name__)
            elif hasattr(tool, 'agent'):
                tool_names.append(f"agent_{tool.agent.name}")
        
        assert "who_is_assigned" in tool_names
        assert "answer_jira_query" in tool_names
    
    def test_agent_has_sub_agents(self):
        """Test that agent has all required sub-agents."""
        sub_agent_names = [sub_agent.name for sub_agent in agent.sub_agents]
        
        expected_agents = ["jira_agent", "github_repo_agent", "jira_cpa_agent", "cpa_engine_agent"]
        for expected in expected_agents:
            assert any(expected in name for name in sub_agent_names), f"Missing sub-agent: {expected}"


class TestAgentTools:
    """Test agent tool functions."""
    
    @patch('backend.tools.jira.cpa_tools.requests.get')
    @patch.dict('os.environ', {
        'JIRA_SERVER': 'https://test.atlassian.net',
        'JIRA_USERNAME': 'test@example.com',
        'JIRA_API': 'test-token'
    })
    def test_who_is_assigned_success(self, mock_get):
        """Test successful who_is_assigned function."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "fields": {
                "assignee": {
                    "displayName": "John Doe",
                    "emailAddress": "john@example.com"
                }
            }
        }
        mock_get.return_value = mock_response
        
        result = who_is_assigned("TEST-123")
        
        assert result["issue_key"] == "TEST-123"
        assert result["assignee"]["name"] == "John Doe"
        assert result["assignee"]["email"] == "john@example.com"
    
    @patch('backend.tools.jira.cpa_tools.requests.get')
    @patch.dict('os.environ', {
        'JIRA_SERVER': 'https://test.atlassian.net',
        'JIRA_USERNAME': 'test@example.com',
        'JIRA_API': 'test-token'
    })
    def test_who_is_assigned_unassigned(self, mock_get):
        """Test who_is_assigned with unassigned issue."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "fields": {
                "assignee": None
            }
        }
        mock_get.return_value = mock_response
        
        result = who_is_assigned("TEST-123")
        
        assert result["issue_key"] == "TEST-123"
        assert result["assignee"] is None
    
    @patch('backend.tools.jira.cpa_tools.requests.get')
    @patch.dict('os.environ', {
        'JIRA_SERVER': 'https://test.atlassian.net',
        'JIRA_USERNAME': 'test@example.com',
        'JIRA_API': 'test-token'
    })
    def test_who_is_assigned_not_found(self, mock_get):
        """Test who_is_assigned with non-existent issue."""
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        result = who_is_assigned("NONEXISTENT-123")
        
        assert "error" in result
        assert "not found" in result["error"].lower()
    
    @patch.dict('os.environ', {}, clear=True)
    def test_who_is_assigned_missing_env(self):
        """Test who_is_assigned with missing environment variables."""
        result = who_is_assigned("TEST-123")
        
        assert "error" in result
        assert "environment" in result["error"].lower()


class TestSubAgentImports:
    """Test that all sub-agents can be imported successfully."""
    
    def test_import_jira_agent(self):
        """Test importing jira_agent."""
        from backend.agents.sub_agents.jira_agent.agent import jira_agent
        assert jira_agent is not None
        assert hasattr(jira_agent, 'name')
    
    def test_import_github_repo_agent(self):
        """Test importing github_repo_agent."""
        from backend.agents.sub_agents.github_repo_agent.agent import github_repo_agent
        assert github_repo_agent is not None
        assert hasattr(github_repo_agent, 'name')
    
    def test_import_jira_cpa_agent(self):
        """Test importing jira_cpa_agent."""
        from backend.agents.sub_agents.jira_cpa_agent.agent import jira_cpa_agent
        assert jira_cpa_agent is not None
        assert hasattr(jira_cpa_agent, 'name')
    
    def test_import_cpa_engine_agent(self):
        """Test importing cpa_engine_agent."""
        from backend.agents.sub_agents.cpa_engine_agent.agent import cpa_engine_agent
        assert cpa_engine_agent is not None
        assert hasattr(cpa_engine_agent, 'name')
    
    def test_import_formatter_agent(self):
        """Test importing formatter_agent."""
        from backend.agents.sub_agents.formatter_agent.agent import formatter_agent
        assert formatter_agent is not None
        assert hasattr(formatter_agent, 'name')


class TestAgentMocking:
    """Test agent mocking for LLM calls."""
    
    @patch('google.adk.agents.Agent')
    def test_mock_agent_creation(self, mock_agent_class):
        """Test that agents can be mocked properly."""
        mock_agent_instance = Mock()
        mock_agent_instance.name = "test_agent"
        mock_agent_instance.model = "gemini-2.0-flash"
        mock_agent_class.return_value = mock_agent_instance
        
        # Create a new agent instance
        test_agent = mock_agent_class(
            name="test_agent",
            model="gemini-2.0-flash",
            description="Test agent"
        )
        
        assert test_agent.name == "test_agent"
        assert test_agent.model == "gemini-2.0-flash"
    
    def test_mock_function_tool(self):
        """Test mocking of FunctionTool."""
        def mock_function(param: str) -> str:
            return f"Mocked result for {param}"
        
        tool = FunctionTool(mock_function)
        assert tool.func == mock_function
        assert tool.func("test") == "Mocked result for test"
    
    def test_mock_agent_tool(self):
        """Test mocking of AgentTool."""
        mock_agent = Mock()
        mock_agent.name = "mock_sub_agent"
        
        tool = AgentTool(mock_agent)
        assert tool.agent == mock_agent
        assert tool.agent.name == "mock_sub_agent"


class TestAgentInstructions:
    """Test agent instruction parsing and validation."""
    
    def test_agent_instruction_content(self):
        """Test that agent instructions contain required content."""
        instruction = agent.instruction
        
        # Check for key instruction elements
        assert "coordinate" in instruction.lower()
        assert "sub-agent" in instruction.lower()
        assert "jira" in instruction.lower()
        assert "github" in instruction.lower()
        
        # Check for specific tool mentions
        assert "who_is_assigned" in instruction
        assert "answer_jira_query" in instruction
    
    def test_agent_instruction_warnings(self):
        """Test that agent instructions contain important warnings."""
        instruction = agent.instruction
        
        # Check for important warnings about direct tool usage
        assert "do not call" in instruction.lower() or "don't call" in instruction.lower()
        assert "transfer_to_agent" in instruction
    
    def test_agent_instruction_routing_rules(self):
        """Test that agent instructions contain routing rules."""
        instruction = agent.instruction
        
        # Check for routing instructions
        assert "project_key" in instruction
        assert "issue_key" in instruction
        assert "repo_full_name" in instruction or "repository" in instruction.lower()


class TestAgentErrorHandling:
    """Test agent error handling scenarios."""
    
    @patch('backend.tools.jira.cpa_tools.requests.get')
    def test_tool_network_error_handling(self, mock_get):
        """Test tool behavior with network errors."""
        mock_get.side_effect = Exception("Network error")
        
        result = who_is_assigned("TEST-123")
        
        assert "error" in result
        assert isinstance(result["error"], str)
    
    @patch('backend.tools.jira.cpa_tools.requests.get')
    def test_tool_timeout_handling(self, mock_get):
        """Test tool behavior with timeout errors."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout("Request timeout")
        
        result = who_is_assigned("TEST-123")
        
        assert "error" in result
        assert "timeout" in result["error"].lower()
    
    def test_tool_invalid_input_handling(self):
        """Test tool behavior with invalid inputs."""
        # Test with None input
        result = who_is_assigned(None)
        assert "error" in result
        
        # Test with empty string
        result = who_is_assigned("")
        assert "error" in result
        
        # Test with invalid format
        result = who_is_assigned("invalid-format")
        # Should still attempt the call but may return error from API
