"""
Tests for main.py FastAPI endpoints and core functionality.
"""
import pytest
import asyncio
import json
import time
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta

from backend.main import (
    app, create_access_token, _jwt_encode_hs256, _jwt_decode_hs256,
    _b64url_encode, _b64url_decode, _cache_get_issue_status, _cache_put_issue_status,
    _ISSUE_STATUS_CACHE, SECRET_KEY
)


class TestJWTFunctions:
    """Test JWT encoding/decoding functions."""
    
    def test_b64url_encode_decode(self):
        """Test base64 URL-safe encoding and decoding."""
        test_data = b"Hello, World!"
        encoded = _b64url_encode(test_data)
        decoded = _b64url_decode(encoded)
        assert decoded == test_data
    
    def test_jwt_encode_decode_valid(self):
        """Test JWT encoding and decoding with valid token."""
        payload = {"sub": "testuser", "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())}
        token = _jwt_encode_hs256(payload, SECRET_KEY)
        decoded = _jwt_decode_hs256(token, SECRET_KEY)
        assert decoded["sub"] == "testuser"
    
    def test_jwt_decode_expired_token(self):
        """Test JWT decoding with expired token."""
        payload = {"sub": "testuser", "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())}
        token = _jwt_encode_hs256(payload, SECRET_KEY)
        
        with pytest.raises(Exception) as exc_info:
            _jwt_decode_hs256(token, SECRET_KEY)
        assert "expired" in str(exc_info.value).lower()
    
    def test_jwt_decode_malformed_token(self):
        """Test JWT decoding with malformed token."""
        with pytest.raises(Exception) as exc_info:
            _jwt_decode_hs256("invalid.token", SECRET_KEY)
        assert "malformed" in str(exc_info.value).lower()
    
    def test_jwt_decode_invalid_signature(self):
        """Test JWT decoding with invalid signature."""
        payload = {"sub": "testuser", "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())}
        token = _jwt_encode_hs256(payload, "wrong-key")
        
        with pytest.raises(Exception) as exc_info:
            _jwt_decode_hs256(token, SECRET_KEY)
        assert "signature" in str(exc_info.value).lower()
    
    def test_create_access_token(self):
        """Test access token creation."""
        data = {"sub": "testuser"}
        token = create_access_token(data)
        decoded = _jwt_decode_hs256(token, SECRET_KEY)
        assert decoded["sub"] == "testuser"
        assert "exp" in decoded


class TestCacheFunctions:
    """Test caching functions."""
    
    def setup_method(self):
        """Clear cache before each test."""
        _ISSUE_STATUS_CACHE.clear()
    
    def test_cache_put_get_valid(self):
        """Test putting and getting valid cache data."""
        test_data = {"key": "TEST-123", "status": "In Progress"}
        _cache_put_issue_status("TEST-123", test_data)
        
        retrieved = _cache_get_issue_status("TEST-123")
        assert retrieved == test_data
    
    def test_cache_get_nonexistent(self):
        """Test getting non-existent cache data."""
        result = _cache_get_issue_status("NONEXISTENT-123")
        assert result is None
    
    def test_cache_get_expired(self):
        """Test getting expired cache data."""
        test_data = {"key": "TEST-123", "status": "In Progress"}
        # Manually set expired timestamp
        _ISSUE_STATUS_CACHE["TEST-123"] = (time.time() - 100, test_data)
        
        result = _cache_get_issue_status("TEST-123")
        assert result is None


class TestBasicEndpoints:
    """Test basic FastAPI endpoints."""
    
    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"message": "Hello from backend!"}
    
    def test_debug_ping(self, client):
        """Test debug ping endpoint."""
        response = client.get("/debug/ping")
        assert response.status_code == 200
        assert response.json() == {"pong": True}


class TestAuthEndpoints:
    """Test authentication endpoints."""
    
    @patch('backend.main.bcrypt.verify')
    def test_login_success(self, mock_verify, client, test_db, mock_env_vars):
        """Test successful login."""
        mock_verify.return_value = True
        
        # Setup test user in database
        db = next(test_db())
        db.execute(
            "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, hashed_password TEXT, skills TEXT)"
        )
        db.execute(
            "INSERT INTO users (username, hashed_password, skills) VALUES (?, ?, ?)",
            ("testuser", "$2b$12$test.hash", "{}")
        )
        db.commit()
        
        response = client.post("/login", json={
            "username": "testuser",
            "password": "testpass"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["username"] == "testuser"
        assert data["token_type"] == "bearer"
    
    @patch('backend.main.bcrypt.verify')
    def test_login_invalid_credentials(self, mock_verify, client, test_db):
        """Test login with invalid credentials."""
        mock_verify.return_value = False
        
        # Setup test user in database
        db = next(test_db())
        db.execute(
            "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, hashed_password TEXT, skills TEXT)"
        )
        db.execute(
            "INSERT INTO users (username, hashed_password, skills) VALUES (?, ?, ?)",
            ("testuser", "$2b$12$test.hash", "{}")
        )
        db.commit()
        
        response = client.post("/login", json={
            "username": "testuser",
            "password": "wrongpass"
        })
        
        assert response.status_code == 401
        assert "Invalid credentials" in response.json()["detail"]
    
    def test_login_user_not_found(self, client, test_db):
        """Test login with non-existent user."""
        response = client.post("/login", json={
            "username": "nonexistent",
            "password": "testpass"
        })
        
        assert response.status_code == 401
    
    @patch('backend.main.bcrypt.hash')
    def test_register_success(self, mock_hash, client, test_db):
        """Test successful registration."""
        mock_hash.return_value = "$2b$12$hashed.password"
        
        # Setup database
        db = next(test_db())
        db.execute(
            "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, hashed_password TEXT, skills TEXT)"
        )
        db.commit()
        
        response = client.post("/register", json={
            "username": "newuser",
            "password": "newpass"
        })
        
        assert response.status_code == 200
        assert response.json()["message"] == "Registration successful"
    
    def test_register_existing_user(self, client, test_db):
        """Test registration with existing username."""
        # Setup database with existing user
        db = next(test_db())
        db.execute(
            "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, hashed_password TEXT, skills TEXT)"
        )
        db.execute(
            "INSERT INTO users (username, hashed_password, skills) VALUES (?, ?, ?)",
            ("existinguser", "$2b$12$test.hash", "{}")
        )
        db.commit()
        
        response = client.post("/register", json={
            "username": "existinguser",
            "password": "newpass"
        })
        
        assert response.status_code == 409
        assert "already registered" in response.json()["detail"]
    
    def test_auth_me_success(self, authenticated_client, mock_user):
        """Test /auth/me endpoint with valid authentication."""
        response = authenticated_client.get("/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == mock_user.username
        assert data["id"] == mock_user.id
        assert data["skills"] == mock_user.skills
    
    def test_auth_me_unauthorized(self, client):
        """Test /auth/me endpoint without authentication."""
        response = client.get("/auth/me")
        assert response.status_code == 401


class TestCodinatorAgent:
    """Test the codinator agent endpoint."""
    
    @pytest.mark.asyncio
    async def test_run_agent_success(self, authenticated_client, mock_llm_calls):
        """Test successful agent run."""
        response = authenticated_client.post("/codinator/run-agent", json={
            "prompt": "Test prompt"
        })
        
        assert response.status_code == 200
        # Should return formatted response from formatter agent
        assert isinstance(response.json(), str)
    
    @pytest.mark.asyncio
    async def test_run_agent_empty_prompt(self, authenticated_client):
        """Test agent run with empty prompt."""
        response = authenticated_client.post("/codinator/run-agent", json={
            "prompt": ""
        })
        
        assert response.status_code == 422
        assert "Missing 'prompt'" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_run_agent_jira_status_prefilter(self, authenticated_client):
        """Test agent run with Jira status query that gets pre-filtered."""
        response = authenticated_client.post("/codinator/run-agent", json={
            "prompt": "what is the status of issue ABC-123"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["ui"] == "jira_status"
        assert data["key"] == "ABC-123"
    
    @pytest.mark.asyncio
    async def test_run_agent_eta_prefilter(self, authenticated_client):
        """Test agent run with ETA query that gets pre-filtered."""
        response = authenticated_client.post("/codinator/run-agent", json={
            "prompt": "when can I expect issue ABC-123 to be complete"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["ui"] == "eta_estimate"
        assert data["issue_key"] == "ABC-123"
    
    def test_run_agent_unauthorized(self, client):
        """Test agent run without authentication."""
        response = client.post("/codinator/run-agent", json={
            "prompt": "Test prompt"
        })
        
        assert response.status_code == 401


class TestJiraEndpoints:
    """Test Jira-related endpoints."""
    
    @patch('backend.main.requests.get')
    def test_jira_issue_status_success(self, mock_get, authenticated_client, mock_jira_response, mock_env_vars):
        """Test successful Jira issue status retrieval."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = mock_jira_response
        mock_get.return_value = mock_response
        
        response = authenticated_client.get("/jira/issue-status?key=TEST-123")
        
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "TEST-123"
        assert data["name"] == "Test Issue"
        assert data["status"] == "In Progress"
    
    @patch('backend.main.requests.get')
    def test_jira_issue_status_not_found(self, mock_get, authenticated_client, mock_env_vars):
        """Test Jira issue status with non-existent issue."""
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        response = authenticated_client.get("/jira/issue-status?key=NONEXISTENT-123")
        
        assert response.status_code == 404
    
    @patch('backend.main._fetch_active_sprint')
    @patch('backend.main._fetch_issues_in_active_sprint')
    def test_jira_sprint_status_success(self, mock_fetch_issues, mock_fetch_sprint, authenticated_client, mock_env_vars):
        """Test successful Jira sprint status retrieval."""
        mock_fetch_sprint.return_value = {"name": "Test Sprint"}
        mock_fetch_issues.return_value = (
            {
                "sprint": {
                    "name": "Test Sprint",
                    "startDate": "2024-01-01",
                    "endDate": "2024-01-15"
                },
                "issues": [
                    {"status": "Done"},
                    {"status": "In Progress"},
                    {"status": "Done"}
                ]
            },
            None
        )
        
        response = authenticated_client.get("/jira/sprint-status?project_key=TEST")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Sprint"
        assert data["totalIssues"] == 3
        assert data["completedIssues"] == 2
    
    def test_jira_base_url_success(self, authenticated_client, mock_env_vars):
        """Test Jira base URL endpoint."""
        response = authenticated_client.get("/jira/base-url")
        
        assert response.status_code == 200
        data = response.json()
        assert data["base"] == "https://test-jira.atlassian.net"
    
    def test_jira_endpoints_unauthorized(self, client):
        """Test Jira endpoints without authentication."""
        endpoints = [
            "/jira/issue-status?key=TEST-123",
            "/jira/sprint-status?project_key=TEST",
            "/jira/base-url"
        ]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 401


class TestErrorHandling:
    """Test error handling scenarios."""
    
    @patch('backend.main.runner.run_async')
    @pytest.mark.asyncio
    async def test_agent_timeout(self, mock_run_async, authenticated_client):
        """Test agent timeout handling."""
        # Mock a long-running operation that times out
        async def slow_generator():
            await asyncio.sleep(50)  # Longer than timeout
            yield Mock()
        
        mock_run_async.return_value = slow_generator()
        
        response = authenticated_client.post("/codinator/run-agent", json={
            "prompt": "Test prompt"
        })
        
        assert response.status_code == 504
        assert "timeout" in response.json()["detail"].lower()
    
    @patch('backend.main.runner.run_async')
    @pytest.mark.asyncio
    async def test_agent_empty_response(self, mock_run_async, authenticated_client):
        """Test handling of empty agent response."""
        async def empty_generator():
            mock_event = Mock()
            mock_event.is_final_response.return_value = True
            mock_event.content = Mock()
            mock_event.content.parts = []  # Empty parts
            yield mock_event
        
        mock_run_async.return_value = empty_generator()
        
        response = authenticated_client.post("/codinator/run-agent", json={
            "prompt": "Test prompt"
        })
        
        assert response.status_code == 502
        assert "empty response" in response.json()["detail"].lower()
