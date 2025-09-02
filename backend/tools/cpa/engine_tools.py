import os
import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import requests
from requests.auth import HTTPBasicAuth
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.db.database import SessionLocal
from backend.app.db.db_loader import load_project_from_db
from backend.app.db.models import ProjectModel, TaskModel
from backend.tools.jira.cpa_tools import _jira_env, _sp_field_key
from dotenv import load_dotenv
from pathlib import Path

# Ensure environment variables from backend/.env are available when tools are invoked directly
_ENV_PATH = (Path(__file__).parents[2] / ".env")
load_dotenv(dotenv_path=_ENV_PATH)


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


def _estimate_days_from_issue(fields: dict) -> float:
    """Derive an estimate in days from Jira fields. Priority: Story Points -> time estimate -> default 1.0.
    Assumes 1 SP ~= 1 day. If timetracking present, convert seconds to days (8h/day)."""
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


# ------------------------------
# DB upsert helpers
# ------------------------------

def _ensure_project(db: Session, name: str) -> int:
    row = db.execute(text("""
        SELECT id FROM projects WHERE name = :name
    """), {"name": name}).fetchone()
    if row:
        return int(row.id)
    new_row = db.execute(text("""
        INSERT INTO projects (name) VALUES (:name)
        RETURNING id
    """), {"name": name}).fetchone()
    db.commit()
    return int(new_row.id)


def _upsert_user(db: Session, username: str) -> Optional[int]:
    """Ensure user exists; return user id if available, else None."""
    if not username:
        return None
    try:
        row = db.execute(text("""
            SELECT id FROM users WHERE username = :u
        """), {"u": username}).fetchone()
        if row:
            return int(row.id)
        # Insert with empty password and empty skills JSONB
        new_row = db.execute(text("""
            INSERT INTO users (username, hashed_password, skills)
            VALUES (:u, :hp, :skills)
            RETURNING id
        """), {"u": username, "hp": "", "skills": json.dumps({})}).fetchone()
        db.commit()
        return int(new_row.id) if new_row else None
    except Exception:
        # Best-effort; do not fail refresh if users table has constraints
        db.rollback()
        return None


def _task_table_columns(db: Session) -> dict:
    """Return mapping of column_name -> data_type for 'tasks' table."""
    rows = db.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'tasks'
    """)).fetchall()
    return {r.column_name: r.data_type for r in rows}


def _upsert_task(db: Session, project_id: int, task_id: str, name: str, estimate_days: float,
                 assignee: Optional[str], end_date: Optional[str]):
    # Normalize date to date string if present
    end_dt_sql = None
    if end_date:
        try:
            end_dt_sql = datetime.fromisoformat(end_date.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            end_dt_sql = None
    cols = _task_table_columns(db)
    has_assignee_id = 'assignee_id' in cols
    has_assignee = 'assignee' in cols
    assignee_is_int = (cols.get('assignee') == 'integer') if has_assignee else False

    user_id: Optional[int] = None
    if assignee and (has_assignee_id or assignee_is_int):
        user_id = _upsert_user(db, assignee)

    if has_assignee_id:
        db.execute(text("""
            INSERT INTO tasks (id, project_id, name, estimate_days, end_date, assignee_id)
            VALUES (:id, :pid, :name, :est, :end_date, :assignee_id)
            ON CONFLICT (id) DO UPDATE SET
              project_id = EXCLUDED.project_id,
              name = EXCLUDED.name,
              estimate_days = EXCLUDED.estimate_days,
              end_date = EXCLUDED.end_date,
              assignee_id = EXCLUDED.assignee_id
        """), {
            "id": task_id,
            "pid": project_id,
            "name": name or task_id,
            "est": float(estimate_days or 1.0),
            "end_date": end_dt_sql,
            "assignee_id": user_id,
        })
    elif has_assignee and assignee_is_int:
        db.execute(text("""
            INSERT INTO tasks (id, project_id, name, estimate_days, end_date, assignee)
            VALUES (:id, :pid, :name, :est, :end_date, :assignee)
            ON CONFLICT (id) DO UPDATE SET
              project_id = EXCLUDED.project_id,
              name = EXCLUDED.name,
              estimate_days = EXCLUDED.estimate_days,
              end_date = EXCLUDED.end_date,
              assignee = EXCLUDED.assignee
        """), {
            "id": task_id,
            "pid": project_id,
            "name": name or task_id,
            "est": float(estimate_days or 1.0),
            "end_date": end_dt_sql,
            "assignee": user_id,
        })
    elif has_assignee:
        db.execute(text("""
            INSERT INTO tasks (id, project_id, name, estimate_days, end_date, assignee)
            VALUES (:id, :pid, :name, :est, :end_date, :assignee)
            ON CONFLICT (id) DO UPDATE SET
              project_id = EXCLUDED.project_id,
              name = EXCLUDED.name,
              estimate_days = EXCLUDED.estimate_days,
              end_date = EXCLUDED.end_date,
              assignee = EXCLUDED.assignee
        """), {
            "id": task_id,
            "pid": project_id,
            "name": name or task_id,
            "est": float(estimate_days or 1.0),
            "end_date": end_dt_sql,
            "assignee": assignee,
        })
    else:
        db.execute(text("""
            INSERT INTO tasks (id, project_id, name, estimate_days, end_date)
            VALUES (:id, :pid, :name, :est, :end_date)
            ON CONFLICT (id) DO UPDATE SET
              project_id = EXCLUDED.project_id,
              name = EXCLUDED.name,
              estimate_days = EXCLUDED.estimate_days,
              end_date = EXCLUDED.end_date
        """), {
            "id": task_id,
            "pid": project_id,
            "name": name or task_id,
            "est": float(estimate_days or 1.0),
            "end_date": end_dt_sql,
        })


def _replace_dependencies(db: Session, task_id: str, depends_on: List[str]):
    # Clear existing, then insert
    db.execute(text("""
        DELETE FROM dependencies WHERE task_id = :tid
    """), {"tid": task_id})
    for dep in depends_on:
        if dep and dep != task_id:
            db.execute(text("""
                INSERT INTO dependencies (task_id, depends_on) VALUES (:tid, :dep)
                ON CONFLICT DO NOTHING
            """), {"tid": task_id, "dep": dep})


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
            est_days = _estimate_days_from_issue(fields)
            deps = _parse_dependencies(fields)

            # Try upsert user
            if assignee:
                _upsert_user(db, assignee)

            # Determine if task exists
            existing = db.execute(text("""
                SELECT id FROM tasks WHERE id = :id
            """), {"id": key}).fetchone()
            _upsert_task(db, project_id, key, name, est_days, assignee, duedate)
            _replace_dependencies(db, key, deps)
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


# ------------------------------
# CPA computation
# ------------------------------

def _topo_sort(nodes: List[str], edges: Dict[str, List[str]]) -> List[str]:
    from collections import deque, defaultdict
    indeg = {u: 0 for u in nodes}
    for u in nodes:
        for v in edges.get(u, []):
            if v in indeg:
                indeg[v] += 1
    q = deque([u for u, d in indeg.items() if d == 0])
    order: List[str] = []
    while q:
        u = q.popleft()
        order.append(u)
        for v in edges.get(u, []):
            if v in indeg:
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
    if len(order) != len(nodes):
        # Cycle detected; fall back to input order
        return nodes[:]
    return order


def _build_graph(project: ProjectModel) -> Tuple[List[str], Dict[str, List[str]], Dict[str, float]]:
    nodes = [t.id for t in project.tasks]
    succ: Dict[str, List[str]] = {t.id: [] for t in project.tasks}
    dur: Dict[str, float] = {t.id: max(0.0, float(t.estimate_days or 0.0)) for t in project.tasks}
    # Build successor map from dependencies (edge dep -> task)
    for t in project.tasks:
        for d in (t.dependencies or []):
            if d in succ:
                succ.setdefault(d, []).append(t.id)
    return nodes, succ, dur


def _run_cpa_calc(project: ProjectModel) -> dict:
    nodes, succ, dur = _build_graph(project)
    order = _topo_sort(nodes, succ)
    # Forward pass: ES/EF
    ES: Dict[str, float] = {u: 0.0 for u in nodes}
    EF: Dict[str, float] = {u: dur[u] for u in nodes}
    preds: Dict[str, List[str]] = {u: [] for u in nodes}
    for u in nodes:
        for v in succ.get(u, []):
            preds[v].append(u)
    for u in order:
        if preds[u]:
            ES[u] = max(EF[p] for p in preds[u])
        EF[u] = ES[u] + dur[u]
    project_duration = max((EF[u] for u in nodes), default=0.0)
    # Backward pass: LS/LF
    LF: Dict[str, float] = {u: project_duration for u in nodes}
    LS: Dict[str, float] = {u: project_duration - dur[u] for u in nodes}
    for u in reversed(order):
        if succ.get(u):
            LF[u] = min(LS[v] for v in succ[u])
            LS[u] = LF[u] - dur[u]
    slack: Dict[str, float] = {u: max(0.0, LS[u] - ES[u]) for u in nodes}
    # Critical path: tasks with zero slack; build ordered path by following longest path
    crit_set = {u for u in nodes if abs(slack[u]) < 1e-9}
    # Build an ordered critical path by filtering order
    critical_path = [u for u in order if u in crit_set]
    return {
        "project_duration": project_duration,
        "tasks": [
            {
                "id": u,
                "duration": dur[u],
                "ES": ES[u],
                "EF": EF[u],
                "LS": LS[u],
                "LF": LF[u],
                "slack": slack[u],
                "isCritical": u in crit_set,
            }
            for u in order
        ],
        "critical_path": critical_path,
    }


def run_cpa(project_id: int) -> dict:
    """Run CPA for a project id using DB data. Returns JSON with per-task metrics and project duration."""
    db = SessionLocal()
    try:
        project = load_project_from_db(db, project_id)
        result = _run_cpa_calc(project)
        return {
            "project_id": project_id,
            "project_name": project.name,
            **result,
        }
    finally:
        db.close()


essential_keys = ["id", "ES", "EF", "LS", "LF", "slack", "duration", "isCritical"]


def get_critical_path(project_id: int) -> dict:
    """Return ordered list of tasks on the critical path."""
    result = run_cpa(project_id)
    return {
        "project_id": project_id,
        "critical_path": result.get("critical_path", []),
    }


def get_task_slack(task_id: str) -> dict:
    """Return slack for a specific task. Determines project via task lookup."""
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT project_id FROM tasks WHERE id = :id
        """), {"id": task_id}).fetchone()
        if not row:
            return {"task_id": task_id, "error": "task not found"}
        project_id = int(row.project_id)
        result = run_cpa(project_id)
        task_map = {t["id"]: t for t in result.get("tasks", [])}
        t = task_map.get(task_id)
        if not t:
            return {"task_id": task_id, "project_id": project_id, "error": "task not in project"}
        return {"task_id": task_id, "project_id": project_id, "slack": t.get("slack", 0.0)}
    finally:
        db.close()


def get_project_duration(project_id: int) -> dict:
    result = run_cpa(project_id)
    return {"project_id": project_id, "duration": result.get("project_duration", 0.0)}


def summarize_current_sprint_cpa(project_key: str) -> dict:
    """High-level helper: refresh from Jira then run CPA and return a concise summary JSON.
    This is intended to be called from chat by the CPA Engine Agent.
    """
    ref = refresh_from_jira(project_key)
    project_id = ref.get("project_id")
    if not project_id:
        return {"project_key": project_key, "error": "project sync failed"}
    res = run_cpa(project_id)
    tasks = res.get("tasks", [])
    critical_path = res.get("critical_path", [])
    crit_count = sum(1 for t in tasks if t.get("isCritical"))
    return {
        "project_key": project_key,
        "project_id": project_id,
        "tasks_count": len(tasks),
        "critical_count": crit_count,
        "project_duration": res.get("project_duration", 0.0),
        "critical_path": critical_path,
        "sample": tasks[:5],
    }
