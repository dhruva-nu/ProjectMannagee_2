import json
from datetime import datetime, date
from typing import Dict, List, Tuple, Optional

import requests
from requests.auth import HTTPBasicAuth
from sqlalchemy import text
from dotenv import load_dotenv
from pathlib import Path

try:
    # When running inside backend/ (e.g., uvicorn main:app)
    from app.db.database import SessionLocal
except ModuleNotFoundError:
    # When importing as backend.* from project root
    from backend.app.db.database import SessionLocal

try:
    from tools.jira.cpa_tools import _jira_env, _sp_field_key
except ModuleNotFoundError:
    from backend.tools.jira.cpa_tools import _jira_env, _sp_field_key

from .db import _ensure_project, _upsert_user, _upsert_task, _replace_dependencies

# Ensure environment variables from backend/.env are available when tools are invoked directly
_ENV_PATH = (Path(__file__).parents[3] / ".env")
load_dotenv(dotenv_path=_ENV_PATH)

# ------------------------------
# Lightweight in-memory cache (TTL) to reduce repeated Jira calls
# ------------------------------
_JIRA_CACHE: Dict[Tuple[str, str], Tuple[float, List[dict]]] = {}

def _cached_current_sprint_issues(project_key: str, ttl_seconds: int = 60) -> List[dict]:
    """Cache wrapper for _jira_search_current_sprint_issues to reduce load.
    Keyed by ("current_sprint", project_key) and expires after ttl_seconds.
    """
    now_ts = datetime.utcnow().timestamp()
    cache_key = ("current_sprint", project_key)
    entry = _JIRA_CACHE.get(cache_key)
    if entry is not None:
        ts, issues = entry
        if (now_ts - ts) < ttl_seconds:
            return issues
    issues = _jira_search_current_sprint_issues(project_key)
    _JIRA_CACHE[cache_key] = (now_ts, issues)
    return issues


# ------------------------------
# Helpers: Jira fetch and parsing
# ------------------------------

def _jira_search_project_issues(project_key: str, max_results: int = 100) -> List[dict]:
    """Fetch all issues for a Jira project via JQL search (Cloud v3 API)."""
    jira_server, jira_username, jira_api_token = _jira_env()
    auth = HTTPBasicAuth(jira_username, jira_api_token)
    headers = {"Accept": "application/json"}
    jql = f"project={project_key} ORDER BY created ASC"
    start_at = 0
    out: List[dict] = []
    fields = [
        "summary",
        "assignee",
        "duedate",
        "issuelinks",
        "issuetype",
        "status",
        "timetracking",
        "aggregatetimeoriginalestimate",
    ]
    sp_key = _sp_field_key()
    if sp_key:
        fields.append(sp_key)

    while True:
        params = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": ",".join(fields),
        }
        url = f"{jira_server}/rest/api/3/search"
        resp = requests.get(url, headers=headers, auth=auth, params=params)
        resp.raise_for_status()
        data = resp.json()
        issues = data.get("issues", [])
        out.extend(issues)
        if start_at + max_results >= data.get("total", 0):
            break
        start_at += max_results
    return out


def _jira_search_current_sprint_issues(project_key: str, max_results: int = 100) -> List[dict]:
    """Fetch issues that are in the current open sprint for the given project.
    Uses JQL: project=<key> AND sprint in openSprints(). Includes 'sprint' field to detect dates if available.
    """
    jira_server, jira_username, jira_api_token = _jira_env()
    auth = HTTPBasicAuth(jira_username, jira_api_token)
    headers = {"Accept": "application/json"}
    jql = f"project={project_key} AND sprint in openSprints() ORDER BY created ASC"
    start_at = 0
    out: List[dict] = []
    fields = [
        "summary",
        "assignee",
        "duedate",
        "issuelinks",
        "issuetype",
        "status",
        "timetracking",
        "aggregatetimeoriginalestimate",
        "sprint",
    ]
    sp_key = _sp_field_key()
    if sp_key:
        fields.append(sp_key)

    while True:
        params = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": ",".join(fields),
        }
        url = f"{jira_server}/rest/api/3/search"
        resp = requests.get(url, headers=headers, auth=auth, params=params)
        resp.raise_for_status()
        data = resp.json()
        issues = data.get("issues", [])
        out.extend(issues)
        if start_at + max_results >= data.get("total", 0):
            break
        start_at += max_results
    return out


def _get_task_duration(fields: dict) -> float:
    """Derive a task duration from Jira fields. Priority: Story Points -> time estimate (converted to days) -> default 1.0.
    If Story Points are available, they are used directly as the duration unit. Otherwise, time estimates are converted to days (assuming 8h/day)."""
    sp_key = _sp_field_key()
    if sp_key and fields.get(sp_key) is not None:
        try:
            return float(fields.get(sp_key))
        except (TypeError, ValueError):
            pass
    # Jira time estimates are seconds. Prefer aggregate original estimate.
    seconds = fields.get("aggregatetimeoriginalestimate")
    if isinstance(seconds, (int, float)) and seconds > 0:
        return float(seconds) / (60 * 60 * 8)
    tt = fields.get("timetracking") or {}
    orig = tt.get("originalEstimateSeconds")
    if isinstance(orig, (int, float)) and orig > 0:
        return float(orig) / (60 * 60 * 8)
    return 1.0


def _parse_dependencies(fields: dict) -> List[str]:
    """Return list of issue keys this issue depends on (blocked by)."""
    deps: List[str] = []
    for link in (fields.get("issuelinks") or []):
        link_type = (link.get("type") or {})
        inward_desc = (link_type.get("inward") or "").lower()
        type_name = (link_type.get("name") or "").lower()
        inward_issue = link.get("inwardIssue")
        if inward_issue and ("blocked" in inward_desc or type_name in {"blocks", "dependency", "depends"}):
            key = inward_issue.get("key")
            if key:
                deps.append(key)
    return deps

def _parse_iso_date(d: Optional[str]) -> Optional[date]:
    if not d:
        return None
    try:
        # Jira dates may be like '2025-09-01' or ISO with Z
        if len(d) == 10:
            return datetime.strptime(d, "%Y-%m-%d").date()
        return datetime.fromisoformat(d.replace("Z", "+00:00")).date()
    except Exception:
        return None


def _extract_sprint_dates(issues: List[dict]) -> Tuple[Optional[date], Optional[date]]:
    """Try to infer sprint start/end dates from the 'sprint' field if present on any issue."""
    start: Optional[date] = None
    end: Optional[date] = None
    for iss in issues:
        fields = iss.get("fields", {})
        sprint_field = fields.get("sprint")
        # Cloud may return a single object or list depending on config; handle both
        sprints = sprint_field if isinstance(sprint_field, list) else ([sprint_field] if sprint_field else [])
        for s in sprints:
            if not isinstance(s, dict):
                continue
            # Some Jira return string in 'name' and full data in 'startDate', 'endDate'
            s_start = _parse_iso_date(s.get("startDate"))
            s_end = _parse_iso_date(s.get("endDate"))
            if s_start and (start is None or s_start < start):
                start = s_start
            if s_end and (end is None or s_end > end):
                end = s_end
    return start, end

# ------------------------------
# Public tools (to be wrapped by FunctionTool)
# ------------------------------

def refresh_from_jira(project_key: str) -> dict:
    """Sync latest Jira issues for a project into the DB.
    Returns JSON: {"project_id", "project_key", "issue_count", "inserted": n, "updated": m}
    """
    issues = _jira_search_project_issues(project_key)
    db = SessionLocal()
    try:
        project_id = _ensure_project(db, project_key)
        inserted = 0
        updated = 0
        for issue in issues:
            key = issue.get("key")
            fields = issue.get("fields", {})
            name = fields.get("summary")
            assignee = (fields.get("assignee") or {}).get("displayName") if fields.get("assignee") else None
            duedate = fields.get("duedate")
            est_duration = _get_task_duration(fields)
            deps = _parse_dependencies(fields)

            # Try upsert user
            if assignee:
                _upsert_user(db, assignee)

            # Determine if task exists
            existing = db.execute(text("""
                SELECT id FROM tasks WHERE id = :id
            """), {"id": key}).fetchone()
            _upsert_task(db, project_id, key, name, est_duration, assignee, duedate)
            _replace_dependencies(db, project_id, key, deps)
            if existing:
                updated += 1
            else:
                inserted += 1
        db.commit()
        return {
            "project_id": project_id,
            "project_key": project_key,
            "issue_count": len(issues),
            "inserted": inserted,
            "updated": updated,
        }
    finally:
        db.close()

def refresh_sprint_from_jira(project_key: str) -> dict:
    """Sync latest Jira issues for a project's current sprint into the DB.
    Returns JSON: {"project_id", "project_key", "issue_count", "inserted": n, "updated": m}
    """
    issues = _cached_current_sprint_issues(project_key)
    db = SessionLocal()
    try:
        project_id = _ensure_project(db, project_key)
        inserted = 0
        updated = 0
        for issue in issues:
            key = issue.get("key")
            fields = issue.get("fields", {})
            name = fields.get("summary")
            assignee = (fields.get("assignee") or {}).get("displayName") if fields.get("assignee") else None
            duedate = fields.get("duedate")
            est_duration = _get_task_duration(fields)
            deps = _parse_dependencies(fields)

            # Try upsert user
            if assignee:
                _upsert_user(db, assignee)

            # Determine if task exists
            existing = db.execute(text("""
                SELECT id FROM tasks WHERE id = :id
            """), {"id": key}).fetchone()
            _upsert_task(db, project_id, key, name, est_duration, assignee, duedate)
            _replace_dependencies(db, project_id, key, deps)
            if existing:
                updated += 1
            else:
                inserted += 1
        db.commit()
        return {
            "project_id": project_id,
            "project_key": project_key,
            "issue_count": len(issues),
            "inserted": inserted,
            "updated": updated,
        }
    finally:
        db.close()
