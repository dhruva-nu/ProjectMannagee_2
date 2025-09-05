"""
Additional tests for Jira ETA graph and sprint completion endpoints in main.py.
We monkeypatch the CPA engine modules imported at runtime to avoid real logic and external calls.
"""
import types
import sys
import pytest
from unittest.mock import Mock

from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture
def client_authenticated(authenticated_client):
    # alias for readability
    return authenticated_client


@pytest.fixture(autouse=True)
def inject_fake_cpa_modules(monkeypatch):
    """Inject fake CPA engine modules so that runtime imports in endpoints resolve to mocks."""
    # Fake sprint_eta module
    sprint_eta = types.ModuleType("sprint_eta")

    def fake_compute_eta_range_for_issue_current_sprint(project_key: str, issue_key: str):
        return {
            "optimistic_days": 3,
            "pessimistic_days": 7,
            "optimistic_schedule": [
                {"day": 1, "tasks": [issue_key]}
            ],
            "pessimistic_schedule": [
                {"day": 1, "tasks": [issue_key]}
            ],
            "optimistic_critical_path": [issue_key],
            "pessimistic_blockers": [],
            "summary": f"ETA for {issue_key} in project {project_key}"
        }

    sprint_eta.compute_eta_range_for_issue_current_sprint = fake_compute_eta_range_for_issue_current_sprint

    # Fake sprint_dependency module
    sprint_dependency = types.ModuleType("sprint_dependency")

    def fake_current_sprint_dependency_graph(project_key: str):
        return {
            "nodes": {
                f"{project_key}-1": {"assignee": "u1", "duration_days": 2, "dependencies": []},
                f"{project_key}-2": {"assignee": "u2", "duration_days": 1, "dependencies": [f"{project_key}-1"]},
            }
        }

    sprint_dependency.current_sprint_dependency_graph = fake_current_sprint_dependency_graph

    # Provide both import paths used in main.py try/except
    sys.modules['tools.cpa.engine.sprint_eta'] = sprint_eta
    sys.modules['tools.cpa.engine.sprint_dependency'] = sprint_dependency
    sys.modules['backend.tools.cpa.engine.sprint_eta'] = sprint_eta
    sys.modules['backend.tools.cpa.engine.sprint_dependency'] = sprint_dependency

    # Fake sprint_timeline for sprint-completion-if-removed
    sprint_timeline = types.ModuleType("sprint_timeline")

    def fake_sprint_completion_if_issue_removed(project_key: str, removed_issue_key: str):
        return {
            "before": "2024-01-15",
            "after": "2024-01-12",
            "delta_days": 3,
            "removed": removed_issue_key,
        }

    sprint_timeline.sprint_completion_if_issue_removed = fake_sprint_completion_if_issue_removed
    sys.modules['tools.cpa.engine.sprint_timeline'] = sprint_timeline
    sys.modules['backend.tools.cpa.engine.sprint_timeline'] = sprint_timeline


class TestJiraEtaGraphEndpoint:
    def test_eta_graph_success(self, client_authenticated):
        resp = client_authenticated.get("/jira/issue-eta-graph", params={"issue_key": "TEST-123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["issue"] == "TEST-123"
        assert data["project_key"] == "TEST"
        assert data["optimistic_days"] == 3
        assert data["pessimistic_days"] == 7
        assert isinstance(data["nodes"], dict)

    def test_eta_graph_invalid_key(self, client_authenticated):
        resp = client_authenticated.get("/jira/issue-eta-graph", params={"issue_key": "INVALID"})
        assert resp.status_code == 422


class TestSprintCompletionIfRemovedEndpoint:
    def test_sprint_completion_if_removed_success(self, client_authenticated):
        resp = client_authenticated.get("/jira/sprint-completion-if-removed", params={"issue_key": "TEST-123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["removed"] == "TEST-123"
        assert data["delta_days"] == 3

    def test_sprint_completion_if_removed_invalid_key(self, client_authenticated):
        resp = client_authenticated.get("/jira/sprint-completion-if-removed", params={"issue_key": "INVALID"})
        assert resp.status_code == 422
