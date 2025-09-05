"""
Test configuration and fixtures for the backend test suite.
"""
import pytest
import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import the main app and dependencies
from backend.main import app, get_current_user, get_db


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_env_vars():
    """Mock environment variables for testing."""
    env_vars = {
        "JWT_SECRET": "test-secret-key",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "60",
        "JIRA_SERVER": "https://test-jira.atlassian.net",
        "JIRA_USERNAME": "test@example.com",
        "JIRA_API": "test-api-token",
        "GITHUB_TOKEN": "test-github-token",
        "GITHUB_DEFAULT_REPO": "test-org/test-repo",
        "DATABASE_URL": "sqlite:///test.db",
    }
    
    with patch.dict(os.environ, env_vars):
        yield env_vars


@pytest.fixture
def test_db(tmp_path):
    """Create a test SQLite database and override get_db dependency.

    Returns a generator function so tests can do: db = next(test_db())
    """
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        from sqlalchemy import text as _sql_text
        class SessionCompat:
            def __init__(self, s):
                self._s = s
            def execute(self, statement, *args, **kwargs):
                # Support raw SQL strings and positional parameters used in tests
                if isinstance(statement, str):
                    # If using DB-API style '?' placeholders with tuple/list params, route via exec_driver_sql
                    if "?" in statement and args and isinstance(args[0], (tuple, list)) and not kwargs:
                        conn = self._s.connection()
                        return conn.exec_driver_sql(statement, args[0])
                    # Otherwise, use SQLAlchemy text with dict/named params
                    statement = _sql_text(statement)
                return self._s.execute(statement, *args, **kwargs)
            def commit(self):
                return self._s.commit()
            def rollback(self):
                return self._s.rollback()
            def close(self):
                return self._s.close()
            def __getattr__(self, name):
                return getattr(self._s, name)
        try:
            db = TestingSessionLocal()
            yield SessionCompat(db)
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Yield the generator function itself so tests can call next(test_db())
    yield override_get_db
    app.dependency_overrides.clear()


@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    from backend.main import User
    return User(
        id=1,
        username="testuser",
        hashed_password="$2b$12$test.hash",
        skills={"python": 5, "testing": 4}
    )


@pytest.fixture
def authenticated_client(mock_user, test_db):
    """Create a test client with authenticated user."""
    def override_get_current_user():
        return mock_user
    
    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_runner():
    """Mock Google ADK Runner."""
    runner = Mock(spec=Runner)
    runner.app_name = "TestApp"
    
    # Mock async generator for run_async
    async def mock_run_async(*args, **kwargs):
        # Create mock event with final response
        mock_event = Mock()
        mock_event.is_final_response.return_value = True
        mock_event.content = Mock()
        mock_event.content.parts = [Mock(text="Mocked LLM response")]
        yield mock_event
    
    runner.run_async = mock_run_async
    return runner


@pytest.fixture
def mock_session_service():
    """Mock InMemorySessionService."""
    service = Mock(spec=InMemorySessionService)
    service.create_session = AsyncMock()
    return service


@pytest.fixture
def mock_jira_response():
    """Mock Jira API response."""
    return {
        "fields": {
            "summary": "Test Issue",
            "duedate": "2024-12-31",
            "status": {"name": "In Progress"},
            "comment": {
                "comments": [
                    {
                        "author": {"displayName": "Test User"},
                        "body": "Test comment"
                    }
                ]
            }
        }
    }


@pytest.fixture
def mock_github_response():
    """Mock GitHub API response."""
    return [
        {
            "sha": "abc123def456",
            "commit": {
                "message": "Test commit message",
                "author": {
                    "name": "Test Author",
                    "date": "2024-01-01T10:00:00Z"
                }
            }
        }
    ]


@pytest.fixture
def temp_state_file():
    """Create temporary state file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = Path(f.name)
    
    yield temp_path
    
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture(autouse=True)
def mock_llm_calls():
    """Auto-mock runner/session_service instances created in backend.main at import time."""
    with patch('backend.main.runner') as mock_runner, \
         patch('backend.main.formatter_runner') as mock_formatter_runner, \
         patch('backend.main.session_service') as mock_session_service, \
         patch('google.genai.types.Content') as mock_content:

        async def mock_run_async(*args, **kwargs):
            mock_event = Mock()
            mock_event.is_final_response.return_value = True
            mock_event.content = Mock()
            mock_event.content.parts = [Mock(text="Mocked response")]
            yield mock_event

        mock_runner.run_async = mock_run_async
        mock_runner.app_name = "TestApp"
        mock_formatter_runner.run_async = mock_run_async
        mock_formatter_runner.app_name = "TestFormatter"

        mock_session_service.create_session = AsyncMock()

        mock_content.return_value = Mock()

        yield {
            'runner': mock_runner,
            'formatter_runner': mock_formatter_runner,
            'session_service': mock_session_service,
            'content': mock_content
        }


@pytest.fixture
def mock_requests():
    """Mock requests for external API calls."""
    with patch('requests.get') as mock_get, \
         patch('requests.post') as mock_post:
        
        # Default successful response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_response.text = "Success"
        
        mock_get.return_value = mock_response
        mock_post.return_value = mock_response
        
        yield {
            'get': mock_get,
            'post': mock_post,
            'response': mock_response
        }
