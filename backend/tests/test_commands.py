"""
Tests for app/commands.py CLI command handling functionality.
"""
import pytest
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from backend.app.commands import (
    _extract_jira_key, _has_flag, _parse_repo_branch, _state_file_path,
    _save_workday_start, _load_workday_start, _github_commits_since,
    _jira_auth_headers, _jira_count, _jira_summary_since, handle_cli_commands
)


class TestExtractJiraKey:
    """Test Jira key extraction function."""
    
    def test_extract_valid_jira_key(self):
        """Test extraction of valid Jira keys."""
        test_cases = [
            ("ABC-123", "ABC-123"),
            ("what is the status of issue PROJ-456", "PROJ-456"),
            ("Check TESTKEY-789 please", "TESTKEY-789"),
            ("abc-123", "ABC-123"),  # Case insensitive
            ("Issue: MYPROJ-999 needs attention", "MYPROJ-999"),
        ]
        
        for text, expected in test_cases:
            result = _extract_jira_key(text)
            assert result == expected, f"Failed for input: {text}"
    
    def test_extract_invalid_jira_key(self):
        """Test extraction with invalid Jira key patterns."""
        test_cases = [
            "",
            "No jira key here",
            "123-ABC",  # Numbers first
            "A-",  # No number
            "-123",  # No project
            "ABC-",  # No number
            "A_BC-123",  # Underscore in project
        ]
        
        for text in test_cases:
            result = _extract_jira_key(text)
            assert result is None, f"Should be None for input: {text}"
    
    def test_extract_multiple_keys_returns_first(self):
        """Test that first valid key is returned when multiple exist."""
        text = "Check ABC-123 and DEF-456"
        result = _extract_jira_key(text)
        assert result == "ABC-123"


class TestHasFlag:
    """Test flag detection function."""
    
    def test_has_flag_positive(self):
        """Test positive flag detection."""
        test_cases = [
            ("--start day", ["--start day"]),
            ("Please --start day now", ["--start day"]),
            ("  --start-day  ", ["--start-day"]),
            ("Multiple  spaces   --end day", ["--end day"]),
        ]
        
        for text, variants in test_cases:
            result = _has_flag(text, variants)
            assert result is True, f"Failed for: {text}"
    
    def test_has_flag_negative(self):
        """Test negative flag detection."""
        test_cases = [
            ("", ["--start day"]),
            ("start day", ["--start day"]),
            ("--start", ["--start day"]),
            ("day", ["--start day"]),
            (None, ["--start day"]),
        ]
        
        for text, variants in test_cases:
            result = _has_flag(text, variants)
            assert result is False, f"Should be False for: {text}"


class TestParseRepoBranch:
    """Test repository and branch parsing function."""
    
    def test_parse_repo_branch_with_equals(self):
        """Test parsing with equals syntax."""
        test_cases = [
            ("repo=owner/name", ("owner/name", None)),
            ("repository=org/project", ("org/project", None)),
            ("branch=main", (None, "main")),
            ("repo=owner/name branch=develop", ("owner/name", "develop")),
        ]
        
        for text, expected in test_cases:
            result = _parse_repo_branch(text)
            assert result == expected, f"Failed for: {text}"
    
    def test_parse_repo_branch_with_flags(self):
        """Test parsing with flag syntax."""
        test_cases = [
            ("--repo owner/name", ("owner/name", None)),
            ("--branch main", (None, "main")),
            ("--repo owner/name --branch develop", ("owner/name", "develop")),
        ]
        
        for text, expected in test_cases:
            result = _parse_repo_branch(text)
            assert result == expected, f"Failed for: {text}"
    
    def test_parse_repo_branch_fallback(self):
        """Test fallback parsing for owner/repo pattern."""
        test_cases = [
            ("check owner/repo status", ("owner/repo", None)),
            ("multiple owner/repo1 owner/repo2", ("owner/repo1", None)),  # First match
        ]
        
        for text, expected in test_cases:
            result = _parse_repo_branch(text)
            assert result == expected, f"Failed for: {text}"
    
    def test_parse_repo_branch_empty(self):
        """Test parsing with empty or invalid input."""
        test_cases = ["", None, "no repo here", "invalid/"]
        
        for text in test_cases:
            result = _parse_repo_branch(text)
            assert result == (None, None), f"Should return (None, None) for: {text}"


class TestStateFileOperations:
    """Test workday state file operations."""
    
    def test_state_file_path(self):
        """Test state file path generation."""
        path = _state_file_path()
        assert isinstance(path, Path)
        assert path.name == ".workday_state.json"
    
    def test_save_load_workday_start(self, temp_state_file):
        """Test saving and loading workday start data."""
        start_time = "2024-01-01T09:00:00+00:00"
        repo = "owner/repo"
        branch = "main"
        
        # Mock the state file path
        with patch('backend.app.commands._state_file_path', return_value=temp_state_file):
            _save_workday_start(start_time, repo, branch)
            loaded_data = _load_workday_start()
        
        assert loaded_data["start"] == start_time
        assert loaded_data["repo"] == repo
        assert loaded_data["branch"] == branch
    
    def test_save_workday_start_minimal(self, temp_state_file):
        """Test saving workday start with minimal data."""
        start_time = "2024-01-01T09:00:00+00:00"
        
        with patch('backend.app.commands._state_file_path', return_value=temp_state_file):
            _save_workday_start(start_time, None, None)
            loaded_data = _load_workday_start()
        
        assert loaded_data["start"] == start_time
        assert "repo" not in loaded_data
        assert "branch" not in loaded_data
    
    def test_load_workday_start_nonexistent(self):
        """Test loading from non-existent state file."""
        nonexistent_path = Path("/tmp/nonexistent_state.json")
        
        with patch('backend.app.commands._state_file_path', return_value=nonexistent_path):
            result = _load_workday_start()
        
        assert result is None
    
    def test_load_workday_start_invalid_json(self, temp_state_file):
        """Test loading from corrupted state file."""
        temp_state_file.write_text("invalid json content")
        
        with patch('backend.app.commands._state_file_path', return_value=temp_state_file):
            result = _load_workday_start()
        
        assert result is None


class TestGithubCommitsSince:
    """Test GitHub commits retrieval function."""
    
    @patch('backend.app.commands.requests.get')
    @patch.dict('os.environ', {'GITHUB_TOKEN': 'test-token'})
    def test_github_commits_since_success(self, mock_get, mock_github_response):
        """Test successful GitHub commits retrieval."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = mock_github_response
        mock_get.return_value = mock_response
        
        start_dt = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        result = _github_commits_since("owner/repo", start_dt)
        
        assert "Commits for owner/repo" in result
        assert "Test commit message" in result
        assert "Test Author" in result
    
    @patch('backend.app.commands.requests.get')
    @patch.dict('os.environ', {'GITHUB_TOKEN': 'test-token'})
    def test_github_commits_since_no_commits(self, mock_get):
        """Test GitHub commits retrieval with no commits."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = []
        mock_get.return_value = mock_response
        
        start_dt = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        result = _github_commits_since("owner/repo", start_dt)
        
        assert "No commits found" in result
    
    @patch.dict('os.environ', {}, clear=True)
    def test_github_commits_since_no_token(self):
        """Test GitHub commits retrieval without token."""
        start_dt = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        result = _github_commits_since("owner/repo", start_dt)
        
        assert "GitHub environment variable" in result
        assert "not set" in result
    
    @patch('backend.app.commands.requests.get')
    @patch.dict('os.environ', {'GITHUB_TOKEN': 'test-token'})
    def test_github_commits_since_api_error(self, mock_get):
        """Test GitHub commits retrieval with API error."""
        mock_get.side_effect = Exception("API Error")
        
        start_dt = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        result = _github_commits_since("owner/repo", start_dt)
        
        assert "error occurred" in result
        assert "API Error" in result


class TestJiraFunctions:
    """Test Jira-related functions."""
    
    @patch.dict('os.environ', {
        'JIRA_SERVER': 'https://test.atlassian.net',
        'JIRA_USERNAME': 'test@example.com',
        'JIRA_API': 'test-token'
    })
    def test_jira_auth_headers_success(self):
        """Test successful Jira auth headers creation."""
        server, auth = _jira_auth_headers()
        
        assert server == 'https://test.atlassian.net'
        assert auth is not None
    
    @patch.dict('os.environ', {}, clear=True)
    def test_jira_auth_headers_missing_env(self):
        """Test Jira auth headers with missing environment variables."""
        result = _jira_auth_headers()
        
        assert result == (None, None)
    
    @patch('backend.app.commands._jira_auth_headers')
    @patch('backend.app.commands.requests.get')
    def test_jira_count_success(self, mock_get, mock_auth):
        """Test successful Jira count query."""
        mock_auth.return_value = ('https://test.atlassian.net', Mock())
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"total": 5}
        mock_get.return_value = mock_response
        
        result = _jira_count("assignee = currentUser()")
        
        assert result == 5
    
    @patch('backend.app.commands._jira_auth_headers')
    def test_jira_count_no_auth(self, mock_auth):
        """Test Jira count with no authentication."""
        mock_auth.return_value = (None, None)
        
        result = _jira_count("assignee = currentUser()")
        
        assert result is None
    
    @patch('backend.app.commands._jira_count')
    def test_jira_summary_since(self, mock_count):
        """Test Jira summary generation."""
        mock_count.side_effect = [3, 1, 5]  # completed, raised, working
        
        start_dt = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        result = _jira_summary_since(start_dt)
        
        assert result["completed"] == 3
        assert result["raised"] == 1
        assert result["working"] == 5
    
    @patch('backend.app.commands._jira_count')
    def test_jira_summary_since_api_failure(self, mock_count):
        """Test Jira summary with API failures."""
        mock_count.return_value = None
        
        start_dt = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        result = _jira_summary_since(start_dt)
        
        assert result["completed"] == "n/a"
        assert result["raised"] == "n/a"
        assert result["working"] == "n/a"


class TestHandleCliCommands:
    """Test CLI command handling."""
    
    @patch('backend.app.commands._save_workday_start')
    @patch.dict('os.environ', {'GITHUB_DEFAULT_REPO': 'default/repo'})
    def test_handle_start_day_command(self, mock_save):
        """Test --start day command handling."""
        result = handle_cli_commands("--start day")
        
        assert result is not None
        assert "response" in result
        assert "Workday started" in result["response"]
        assert "default/repo" in result["response"]
        mock_save.assert_called_once()
    
    @patch('backend.app.commands._save_workday_start')
    def test_handle_start_day_with_repo(self, mock_save):
        """Test --start day command with specific repo."""
        result = handle_cli_commands("--start day repo=owner/custom")
        
        assert result is not None
        assert "owner/custom" in result["response"]
        mock_save.assert_called_once()
    
    @patch('backend.app.commands._load_workday_start')
    @patch('backend.app.commands._github_commits_since')
    @patch('backend.app.commands._jira_summary_since')
    def test_handle_end_day_command(self, mock_jira, mock_github, mock_load):
        """Test --end day command handling."""
        mock_load.return_value = {
            "start": "2024-01-01T09:00:00+00:00",
            "repo": "owner/repo",
            "branch": "main"
        }
        mock_github.return_value = "Mock commit summary"
        mock_jira.return_value = {"completed": 2, "raised": 1, "working": 3}
        
        result = handle_cli_commands("--end day")
        
        assert result is not None
        assert "response" in result
        assert "Workday summary" in result["response"]
        assert "Completed issues: 2" in result["response"]
        assert "Mock commit summary" in result["response"]
    
    @patch('backend.app.commands._load_workday_start')
    @patch('backend.app.commands._github_commits_since')
    @patch('backend.app.commands._jira_summary_since')
    @patch.dict('os.environ', {'GITHUB_DEFAULT_REPO': 'default/repo'})
    def test_handle_end_day_no_saved_state(self, mock_jira, mock_github, mock_load):
        """Test --end day command without saved state."""
        mock_load.return_value = None
        mock_github.return_value = "Mock commit summary"
        mock_jira.return_value = {"completed": 0, "raised": 0, "working": 1}
        
        result = handle_cli_commands("--end day")
        
        assert result is not None
        assert "default/repo" in result["response"]
    
    def test_handle_non_cli_command(self):
        """Test handling of non-CLI commands."""
        result = handle_cli_commands("regular user prompt")
        
        assert result is None
    
    def test_handle_empty_command(self):
        """Test handling of empty command."""
        result = handle_cli_commands("")
        
        assert result is None
