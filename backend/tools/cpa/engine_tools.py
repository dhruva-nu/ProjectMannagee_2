import os
import json
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional, Set
import math
import heapq

import requests
from requests.auth import HTTPBasicAuth
from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    # When running inside backend/ (e.g., uvicorn main:app)
    from app.db.database import SessionLocal
    from app.db.db_loader import load_project_from_db
    from app.db.models import ProjectModel, TaskModel
except ModuleNotFoundError:
    # When importing as backend.* from project root
    from backend.app.db.database import SessionLocal
    from backend.app.db.db_loader import load_project_from_db
    from backend.app.db.models import ProjectModel, TaskModel
try:
    from tools.jira.cpa_tools import _jira_env, _sp_field_key
except ModuleNotFoundError:
    from backend.tools.jira.cpa_tools import _jira_env, _sp_field_key
from dotenv import load_dotenv
from pathlib import Path

# Ensure environment variables from backend/.env are available when tools are invoked directly
_ENV_PATH = (Path(__file__).parents[2] / ".env")
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


def _upsert_task(db: Session, project_id: int, task_id: str, name: str, est_duration: float,
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
            VALUES (:id, :pid, :name, :est_duration, :end_date, :assignee_id)
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
            "est_duration": float(est_duration or 1.0),
            "end_date": end_dt_sql,
            "assignee_id": user_id,
        })
    elif has_assignee and assignee_is_int:
        db.execute(text("""
            INSERT INTO tasks (id, project_id, name, estimate_days, end_date, assignee)
            VALUES (:id, :pid, :name, :est_duration, :end_date, :assignee)
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
            "est_duration": float(est_duration or 1.0),
            "end_date": end_dt_sql,
            "assignee": user_id,
        })
    elif has_assignee:
        db.execute(text("""
            INSERT INTO tasks (id, project_id, name, estimate_days, end_date, assignee)
            VALUES (:id, :pid, :name, :est_duration, :end_date, :assignee)
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
            "est_duration": float(est_duration or 1.0),
            "end_date": end_dt_sql,
            "assignee": assignee,
        })
    else:
        db.execute(text("""
            INSERT INTO tasks (id, project_id, name, estimate_days, end_date)
            VALUES (:id, :pid, :name, :est_duration, :end_date)
            ON CONFLICT (id) DO UPDATE SET
              project_id = EXCLUDED.project_id,
              name = EXCLUDED.name,
              estimate_days = EXCLUDED.estimate_days,
              end_date = EXCLUDED.end_date
        """), {
            "id": task_id,
            "pid": project_id,
            "name": name or task_id,
            "est_duration": float(est_duration or 1.0),
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


def _build_graph_with_assignees(project: ProjectModel) -> Tuple[
    List[str], Dict[str, List[str]], Dict[str, float], Dict[str, List[str]], Dict[str, Optional[str]]
]:
    """Build DAG from DB project with durations (days), successors, predecessors and assignee per node."""
    nodes = [t.id for t in project.tasks]
    succ: Dict[str, List[str]] = {t.id: [] for t in project.tasks}
    preds: Dict[str, List[str]] = {t.id: [] for t in project.tasks}
    dur: Dict[str, float] = {t.id: max(0.0, float(t.estimate_days or 0.0)) for t in project.tasks}
    assignee: Dict[str, Optional[str]] = {t.id: getattr(t, "assignee", None) for t in project.tasks}
    for t in project.tasks:
        for d in (t.dependencies or []):
            if d in succ:
                succ.setdefault(d, []).append(t.id)
                preds[t.id].append(d)
    return nodes, succ, dur, preds, assignee


def _run_pert_rcpsp_calc(project: ProjectModel) -> dict:
    """Run PERT and extend with RCPSP (single capacity per assignee).
    Returns per-task metrics including both plain PERT and resource-constrained times.
    """
    nodes, succ, dur, preds, assignee = _build_graph_with_assignees(project)
    order = _topo_sort(nodes, succ)

    # 1) Plain PERT (dependencies only)
    ES0: Dict[str, float] = {u: 0.0 for u in nodes}
    EF0: Dict[str, float] = {u: max(0.0, dur[u]) for u in nodes}
    for u in order:
        if preds[u]:
            ES0[u] = max(EF0[p] for p in preds[u])
        EF0[u] = ES0[u] + max(0.0, dur[u])
    makespan0 = max((EF0[u] for u in nodes), default=0.0)

    LF0: Dict[str, float] = {u: makespan0 for u in nodes}
    LS0: Dict[str, float] = {u: makespan0 - max(0.0, dur[u]) for u in nodes}
    for u in reversed(order):
        if succ.get(u):
            LF0[u] = min(LS0[v] for v in succ[u])
            LS0[u] = LF0[u] - max(0.0, dur[u])
    slack0: Dict[str, float] = {u: max(0.0, LS0[u] - ES0[u]) for u in nodes}

    # 2) RCPSP forward pass (dependencies + single-unit capacity per assignee)
    indeg: Dict[str, int] = {k: 0 for k in nodes}
    for v in nodes:
        for p in preds[v]:
            if p in indeg:
                indeg[v] += 1
    ready: List[str] = [k for k, d in indeg.items() if d == 0]
    # deterministic by numeric suffix then id
    def _issue_key_number(k: Optional[str]) -> int:
        try:
            if not k or '-' not in k:
                return 0
            return int(k.rsplit('-', 1)[1])
        except Exception:
            return 0
    ready.sort(key=lambda x: (_issue_key_number(x), x))

    ES: Dict[str, float] = {u: 0.0 for u in nodes}
    EF: Dict[str, float] = {u: 0.0 for u in nodes}
    next_free: Dict[Optional[str], float] = {}
    deps_finish: Dict[str, float] = {u: 0.0 for u in nodes}

    # Min-heap of (finish_time, node)
    heap: List[Tuple[float, str]] = []

    def try_schedule(u: str, current_time: float):
        user = assignee.get(u)
        start_u = max(current_time, next_free.get(user, 0.0), deps_finish.get(u, 0.0))
        ES[u] = start_u
        d = max(0.0, float(dur[u]))
        EF[u] = start_u + d
        next_free[user] = EF[u]
        heapq.heappush(heap, (EF[u], u))

    # Initially schedule all indegree-0 tasks
    current_time = 0.0
    for u in ready:
        try_schedule(u, current_time)

    scheduled = set(ready)
    while heap:
        ft, done = heapq.heappop(heap)
        current_time = ft
        for v in succ.get(done, []):
            deps_finish[v] = max(deps_finish.get(v, 0.0), ft)
            indeg[v] -= 1
            if indeg[v] == 0:
                try_schedule(v, current_time)
                scheduled.add(v)

    makespan = max((EF[u] for u in nodes), default=0.0)

    # 3) RCPSP backward pass (approximate). Respect precedence and resource capacity backwards.
    LF: Dict[str, float] = {u: makespan for u in nodes}
    LS: Dict[str, float] = {u: makespan - max(0.0, dur[u]) for u in nodes}

    # Precedence-based initialization
    for u in reversed(order):
        if succ.get(u):
            LF[u] = min(LS[v] for v in succ[u])
            LS[u] = LF[u] - max(0.0, dur[u])

    # Resource feasibility adjustment: iterate per assignee from latest to earliest
    for _ in range(3):  # a few passes to converge
        by_user: Dict[Optional[str], List[str]] = {}
        for u in nodes:
            by_user.setdefault(assignee.get(u), []).append(u)
        for user, tasks in by_user.items():
            # Sort tasks by current LF descending (latest finishing first)
            tasks_sorted = sorted(tasks, key=lambda k: (LF.get(k, 0.0), EF.get(k, 0.0)), reverse=True)
            latest_free = makespan
            for u in tasks_sorted:
                # Resource-imposed latest finish
                lf_res = latest_free
                # Precedence-imposed latest finish
                lf_pred = LF.get(u, makespan)
                new_lf = min(lf_res, lf_pred)
                new_ls = new_lf - max(0.0, dur[u])
                if new_lf < LF[u] or new_ls < LS[u]:
                    LF[u] = new_lf
                    LS[u] = new_ls
                latest_free = LS[u]

    slack: Dict[str, float] = {u: max(0.0, LS[u] - ES[u]) for u in nodes}

    crit_set = {u for u in nodes if abs(slack[u]) < 1e-9}
    # Order tasks for output: use original topological order
    tasks_out = []
    for u in order:
        tasks_out.append({
            "id": u,
            "assignee": assignee.get(u),
            "duration": dur[u],
            # resource-constrained
            "ES": ES[u],
            "EF": EF[u],
            "LS": LS[u],
            "LF": LF[u],
            "slack": slack[u],
            # plain PERT for reference
            "ES_plain": ES0[u],
            "EF_plain": EF0[u],
            "LS_plain": LS0[u],
            "LF_plain": LF0[u],
            "slack_plain": slack0[u],
            "isCritical": u in crit_set,
        })

    return {
        "project_duration": makespan,
        "tasks": tasks_out,
        "critical_path": [u for u in order if u in crit_set],
    }


def run_cpa(project_id: int) -> dict:
    """Run PERT + RCPSP for a project id using DB data.
    Returns JSON with per-task metrics (resource-constrained ES/EF/LS/LF/Slack) and project duration.
    Also includes plain PERT fields (*_plain) for reference.
    """
    db = SessionLocal()
    try:
        project = load_project_from_db(db, project_id)
        result = _run_pert_rcpsp_calc(project)
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


def get_issue_finish_bounds(project_id: int, issue_id: str) -> dict:
    """Return resource-constrained earliest finish (EF) and latest finish (LF) for a specific issue.
    Falls back to plain PERT values if constrained ones are missing.
    """
    res = run_cpa(project_id)
    task_map = {t.get("id"): t for t in res.get("tasks", [])}
    t = task_map.get(issue_id)
    if not t:
        return {"project_id": project_id, "issue_id": issue_id, "error": "task not found"}
    ef = t.get("EF") if t.get("EF") is not None else t.get("EF_plain")
    lf = t.get("LF") if t.get("LF") is not None else t.get("LF_plain")
    return {
        "project_id": project_id,
        "issue_id": issue_id,
        "earliest_finish": ef,
        "latest_finish": lf,
        "assignee": t.get("assignee"),
        "duration": t.get("duration"),
    }


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


# ------------------------------
# Current sprint CPA with per-assignee timelines and holidays
# ------------------------------

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


def _advance_working_days(start: date, days: int, working_days: Set[int], holidays: Set[date]) -> date:
    """Advance by 'days' working days (1 SP = 1 day). working_days is set of weekday numbers (0=Mon..6=Sun).
    Skip any date not in working_days or in holidays. Returns the date landing AFTER consuming 'days' days; e.g.,
    start Monday + 5 working days -> Friday.
    """
    if days <= 0:
        return start
    d = start
    consumed = 0
    while consumed < days:
        # Count current day if it's a working day and not a holiday
        if d.weekday() in working_days and d not in holidays:
            consumed += 1
            if consumed == days:
                return d
        d = d + timedelta(days=1)
    return d


def _to_date_set(dates: Optional[List[str]]) -> Set[date]:
    out: Set[date] = set()
    for s in (dates or []):
        dt = _parse_iso_date(s)
        if dt:
            out.add(dt)
    return out


def current_sprint_cpa_timeline(
    project_key: str,
    start_on: Optional[str] = None,
    working_days: Optional[List[int]] = None,
    global_holidays: Optional[List[str]] = None,
    holidays_by_user: Optional[Dict[str, List[str]]] = None,
) -> dict:
    """Answer: "What is the CPA of the current sprint?"
    - Fetch all issues in open sprint for project.
    - Estimate durations via Story Points (1 SP = 1 day), fallback to time estimate or 1.
    - Build per-assignee sequential timelines from sprint start date (if available), else 'start_on' param or today.
    - Respect holidays per user and global by skipping those days.
    - Return per-issue estimated completion dates, per-assignee schedules, overall sprint completion (CPA-like estimate).

    Params:
    - start_on: ISO date string to force a start date. If None, use sprint start; else today.
    - working_days: weekdays considered working (0=Mon..6=Sun). Default: all days treated as working.
    - global_holidays: list of ISO dates treated as non-working for all.
    - holidays_by_user: mapping of user displayName -> list of ISO dates of unavailability.
    """
    issues = _cached_current_sprint_issues(project_key)

    # Determine start date
    sprint_start, sprint_end = _extract_sprint_dates(issues)
    start_dt = _parse_iso_date(start_on) if start_on else None
    base_start = sprint_start or start_dt or datetime.utcnow().date()

    # Working calendar
    working_days_set: Set[int] = set(working_days) if working_days is not None else {0,1,2,3,4,5,6}
    global_hols_set: Set[date] = _to_date_set(global_holidays)

    # Prepare per-assignee queues
    sp_key = _sp_field_key()
    items: List[dict] = []
    for iss in issues:
        key = iss.get("key")
        fields = iss.get("fields", {})
        assignee = (fields.get("assignee") or {}).get("displayName") if fields.get("assignee") else "Unassigned"
        duration_days = _get_task_duration(fields)
        # Convert to whole days, but keep fractional with ceil to be safe
        duration_whole = int(math.ceil(max(0.0, float(duration_days)))) or 1
        items.append({
            "key": key,
            "summary": fields.get("summary"),
            "assignee": assignee,
            "story_points": float(fields.get(sp_key)) if (sp_key and fields.get(sp_key) is not None) else None,
            "estimated_days": duration_whole,
        })

    # Group by assignee and schedule sequentially
    by_user: Dict[str, List[dict]] = {}
    for it in items:
        by_user.setdefault(it["assignee"], []).append(it)

    # Ensure deterministic sequencing per assignee: sort by numeric suffix of issue key (e.g., TEST-123)
    def _issue_key_number(k: Optional[str]) -> int:
        try:
            if not k or '-' not in k:
                return 0
            return int(k.rsplit('-', 1)[1])
        except Exception:
            return 0

    # Schedule
    schedules: Dict[str, List[dict]] = {}
    per_issue_completion: Dict[str, str] = {}
    for user, tasks in by_user.items():
        # Stable order within a user's queue
        tasks = sorted(tasks, key=lambda t: (_issue_key_number(t.get("key")), t.get("key") or ""))
        # User-specific holidays
        user_holidays = _to_date_set((holidays_by_user or {}).get(user)) | global_hols_set
        current = base_start
        user_sched: List[dict] = []
        for t in tasks:
            start_d = current
            end_d = _advance_working_days(start_d, t["estimated_days"], working_days_set, user_holidays)
            # Next task starts the day after end_d
            current = end_d + timedelta(days=1)
            entry = {
                "issue": t["key"],
                "summary": t["summary"],
                "assignee": user,
                "start": start_d.isoformat(),
                "end": end_d.isoformat(),
                "days": t["estimated_days"],
            }
            user_sched.append(entry)
            per_issue_completion[t["key"]] = end_d.isoformat()
        schedules[user] = user_sched

    # Overall completion is the max end across all
    all_ends: List[date] = []
    for user, sched in schedules.items():
        for e in sched:
            all_ends.append(_parse_iso_date(e["end"]))
    overall_end = max([d for d in all_ends if d is not None], default=base_start)

    return {
        "project_key": project_key,
        "sprint_start": (sprint_start or base_start).isoformat() if (sprint_start or base_start) else None,
        "sprint_end": sprint_end.isoformat() if sprint_end else None,
        "start_used": base_start.isoformat(),
        "working_days": sorted(list(working_days_set)),
        "issues_count": len(items),
        "per_issue_completion": per_issue_completion,
        "per_assignee_timeline": schedules,
        "overall_completion_date": overall_end.isoformat(),
    }


def estimate_issue_completion_in_current_sprint(
    project_key: str,
    issue_key: str,
    start_on: Optional[str] = None,
    working_days: Optional[List[int]] = None,
    global_holidays: Optional[List[str]] = None,
    holidays_by_user: Optional[Dict[str, List[str]]] = None,
) -> dict:
    """Lightweight estimate for a single issue to minimize load.
    Computes only the target assignee's sequential schedule instead of the full project.
    Uses Story Points = 1 day model and honors holidays.
    """
    # Fetch only current sprint issues once (cached)
    issues = _cached_current_sprint_issues(project_key)

    # Determine sprint start/end from available issues
    sprint_start, sprint_end = _extract_sprint_dates(issues)
    start_dt = _parse_iso_date(start_on) if start_on else None
    base_start = sprint_start or start_dt or datetime.utcnow().date()

    # Working calendar
    working_days_set: Set[int] = set(working_days) if working_days is not None else {0,1,2,3,4,5,6}
    global_hols_set: Set[date] = _to_date_set(global_holidays)

    # Find the target issue and its assignee
    target_issue = None
    for iss in issues:
        if iss.get("key") == issue_key:
            target_issue = iss
            break

    if not target_issue:
        return {
            "project_key": project_key,
            "issue_key": issue_key,
            "error": "issue not found in current sprint",
            "sprint_start": sprint_start.isoformat() if sprint_start else None,
            "sprint_end": sprint_end.isoformat() if sprint_end else None,
        }

    target_fields = target_issue.get("fields", {})
    target_assignee = (target_fields.get("assignee") or {}).get("displayName") if target_fields.get("assignee") else "Unassigned"

    # Build the task list only for the target assignee
    sp_key = _sp_field_key()
    tasks_for_assignee: List[dict] = []
    for iss in issues:
        fields = iss.get("fields", {})
        assignee_name = (fields.get("assignee") or {}).get("displayName") if fields.get("assignee") else "Unassigned"
        if assignee_name != target_assignee:
            continue
        duration_days = _get_task_duration(fields)
        duration_whole = int(math.ceil(max(0.0, float(duration_days)))) or 1
        status_obj = fields.get("status") or {}
        status_name = (status_obj.get("name") or "").strip()
        status_cat_key = ((status_obj.get("statusCategory") or {}).get("key") or "").lower()
        is_done = (status_cat_key == "done") or (status_name.lower() == "done")
        tasks_for_assignee.append({
            "key": iss.get("key"),
            "summary": fields.get("summary"),
            "estimated_days": duration_whole,
            "story_points": float(fields.get(sp_key)) if (sp_key and fields.get(sp_key) is not None) else None,
            "status": status_name,
            "is_done": is_done,
        })

    # Deterministic order by numeric key to mimic team conventions
    def _issue_key_number(k: Optional[str]) -> int:
        try:
            if not k or '-' not in k:
                return 0
            return int(k.rsplit('-', 1)[1])
        except Exception:
            return 0

    tasks_for_assignee = sorted(tasks_for_assignee, key=lambda t: (_issue_key_number(t.get("key")), t.get("key") or ""))

    # Apply user-specific holidays
    user_holidays = _to_date_set((holidays_by_user or {}).get(target_assignee)) | global_hols_set

    # Schedule only this assignee sequentially
    # 1) First consume DONE issues to advance the clock (so they don't push future tasks incorrectly)
    # 2) Then schedule the remaining (non-Done) issues
    current = base_start
    timeline: List[dict] = []
    per_issue_completion: Dict[str, str] = {}

    done_tasks = [t for t in tasks_for_assignee if t.get("is_done")]
    pending_tasks = [t for t in tasks_for_assignee if not t.get("is_done")]

    

    for t in pending_tasks:
        sdt = current
        edt = _advance_working_days(sdt, t["estimated_days"], working_days_set, user_holidays)
        current = edt + timedelta(days=1)
        entry = {
            "issue": t["key"],
            "summary": t["summary"],
            "assignee": target_assignee,
            "start": sdt.isoformat(),
            "end": edt.isoformat(),
            "days": t["estimated_days"],
            "status": t.get("status"),
        }
        timeline.append(entry)
        per_issue_completion[t["key"]] = edt.isoformat()

    completion = per_issue_completion.get(issue_key)
    timeline_entry = next((e for e in timeline if e.get("issue") == issue_key), None)

    return {
        "project_key": project_key,
        "issue_key": issue_key,
        "assignee": target_assignee,
        "estimated_completion_date": completion,
        "timeline": timeline_entry,
        # We avoid computing overall sprint completion to reduce load
        "overall_sprint_completion": None,
        "sprint_start": (sprint_start or base_start).isoformat() if (sprint_start or base_start) else None,
        "sprint_end": sprint_end.isoformat() if sprint_end else None,
    }


# ------------------------------
# Current sprint RCPSP-like scheduler (dependencies + per-assignee sequential work)
# ------------------------------

def _date_after(d: date, days: int) -> date:
    return d + timedelta(days=days)


def _max_date(a: Optional[date], b: Optional[date]) -> Optional[date]:
    if a is None:
        return b
    if b is None:
        return a
    return a if a >= b else b


def current_sprint_dependency_graph(project_key: str) -> dict:
    """Build a weighted dependency graph for issues in the current sprint.
    Nodes store assignee, story points (as days), and dependencies limited to issues present in the sprint.
    """
    issues = _cached_current_sprint_issues(project_key)
    sp_key = _sp_field_key()
    present_keys = {iss.get("key") for iss in issues}
    nodes: Dict[str, dict] = {}
    edges: List[Tuple[str, str]] = []
    for iss in issues:
        key = iss.get("key")
        fields = iss.get("fields", {})
        if not key:
            continue
        assignee = (fields.get("assignee") or {}).get("displayName") if fields.get("assignee") else "Unassigned"
        duration_days = _get_task_duration(fields)
        duration_whole = int(math.ceil(max(0.0, float(duration_days)))) or 1
        # Limit dependencies to those also in this sprint
        deps_all = _parse_dependencies(fields)
        deps = [d for d in deps_all if d in present_keys and d != key]
        nodes[key] = {
            "assignee": assignee,
            "story_points": float(fields.get(sp_key)) if (sp_key and fields.get(sp_key) is not None) else None,
            "duration_days": duration_whole,
            "dependencies": deps,
        }
        for d in deps:
            edges.append((d, key))
    return {"project_key": project_key, "nodes": nodes, "edges": edges}


def format_current_sprint_dependency_graph(graph: dict) -> str:
    """Format the output of current_sprint_dependency_graph() into a human-readable string.
    Shows issue, duration days, and assignee; edges show dependency -> issue.
    """
    project_key = graph.get("project_key")
    nodes: Dict[str, dict] = graph.get("nodes", {})
    edges: List[Tuple[str, str]] = graph.get("edges", [])
    lines: List[str] = []
    lines.append(f"Current Sprint Dependency Graph for project {project_key}")
    lines.append("")
    lines.append("Nodes (issue: days, assignee, story points):")
    def _num(x: str) -> int:
        try:
            return int(x.rsplit('-', 1)[1]) if '-' in x else 0
        except Exception:
            return 0
    for k in sorted(nodes.keys(), key=lambda s: (_num(s), s)):
        nd = nodes[k]
        story_points = nd.get('story_points')
        sp_str = f", SP: {story_points}" if story_points is not None else ""
        lines.append(f" - {k}: {nd.get('duration_days', 0)}d, {nd.get('assignee')}{sp_str}")
    lines.append("")
    lines.append("Edges (dependency -> issue):")
    if edges:
        for u, v in sorted(edges, key=lambda e: (_num(e[0]), e[0], _num(e[1]), e[1])):
            lines.append(f" - {u} -> {v}")
    else:
        lines.append(" - (no dependencies detected)")
    return "\n".join(lines)


def print_current_sprint_dependency_graph_for_issue(issue_key: str) -> str:
    """Infer project key from issue key and print the current sprint dependency graph only."""
    if not issue_key or '-' not in issue_key:
        raise ValueError("issue_key must look like 'PROJ-123'")
    project_key = issue_key.split('-', 1)[0]
    graph = current_sprint_dependency_graph(project_key)
    text = format_current_sprint_dependency_graph(graph)
    try:
        print(text)
    except Exception:
        pass
    return text


def schedule_current_sprint_with_dependencies(
    project_key: str,
    start_on: Optional[str] = None,
    working_days: Optional[List[int]] = None,
    global_holidays: Optional[List[str]] = None,
    holidays_by_user: Optional[Dict[str, List[str]]] = None,
) -> dict:
    """Resource-constrained scheduling for current sprint respecting dependencies and per-assignee sequential work.
    Returns per-issue start/end dates and overall completion.
    """
    issues = _cached_current_sprint_issues(project_key)
    sprint_start, sprint_end = _extract_sprint_dates(issues)
    start_dt = _parse_iso_date(start_on) if start_on else None
    base_start = sprint_start or start_dt or datetime.utcnow().date()

    working_days_set: Set[int] = set(working_days) if working_days is not None else {0,1,2,3,4,5,6}
    global_hols_set: Set[date] = _to_date_set(global_holidays)

    graph = current_sprint_dependency_graph(project_key)
    nodes = graph["nodes"]

    # Build indegrees and successors
    indeg: Dict[str, int] = {k: 0 for k in nodes}
    succ: Dict[str, List[str]] = {k: [] for k in nodes}
    for v, nd in nodes.items():
        for u in nd.get("dependencies", []):
            if u in indeg:
                indeg[v] += 1
                succ.setdefault(u, []).append(v)

    # Assignee availability dates
    next_free: Dict[str, date] = {}
    # Track per-issue schedule
    start_dates: Dict[str, date] = {}
    end_dates: Dict[str, date] = {}

    # Ready queue (issues with indegree 0)
    ready: List[str] = [k for k, d in indeg.items() if d == 0]
    # Min-heap of ongoing tasks by end date: (end_date, issue_key)
    heap: List[Tuple[date, str]] = []

    # Helper to attempt scheduling an issue when its assignee is free
    def try_schedule(k: str, current_date: date):
        nd = nodes[k]
        user = nd["assignee"]
        user_holidays = _to_date_set((holidays_by_user or {}).get(user)) | global_hols_set
        avail = next_free.get(user, base_start)
        sdt = max(current_date, avail)
        edt = _advance_working_days(sdt, nd["duration_days"], working_days_set, user_holidays)
        start_dates[k] = sdt
        end_dates[k] = edt
        # User becomes free the day after end
        next_free[user] = edt + timedelta(days=1)
        heapq.heappush(heap, (edt, k))

    current_date = base_start
    # Deterministic order for ready list by numeric part then key
    def _issue_key_number(k: Optional[str]) -> int:
        try:
            if not k or '-' not in k:
                return 0
            return int(k.rsplit('-', 1)[1])
        except Exception:
            return 0

    ready.sort(key=lambda x: (_issue_key_number(x), x))

    # Initially schedule as many as possible at base_start
    i = 0
    while i < len(ready):
        k = ready[i]
        try_schedule(k, current_date)
        i += 1

    scheduled_count = len(ready)

    # Process events
    while heap:
        edt, done_key = heapq.heappop(heap)
        current_date = edt  # advance time to this completion
        # Reduce indegree of successors
        for v in succ.get(done_key, []):
            indeg[v] -= 1
            if indeg[v] == 0:
                # Newly ready; schedule at the max of current time and assignee availability
                try_schedule(v, current_date)
                scheduled_count += 1

    overall_end = max(end_dates.values()) if end_dates else base_start

    # Prepare outputs
    per_issue = {
        k: {
            "assignee": nodes[k]["assignee"],
            "start": start_dates[k].isoformat(),
            "end": end_dates[k].isoformat(),
            "days": nodes[k]["duration_days"],
            "dependencies": nodes[k]["dependencies"],
        }
        for k in nodes.keys()
    }

    return {
        "project_key": project_key,
        "sprint_start": (sprint_start or base_start).isoformat() if (sprint_start or base_start) else None,
        "sprint_end": sprint_end.isoformat() if sprint_end else None,
        "start_used": base_start.isoformat(),
        "per_issue_schedule": per_issue,
        "overall_completion_date": overall_end.isoformat(),
    }


def expected_completion_for_issue_in_current_sprint(
    project_key: str,
    issue_key: str,
    start_on: Optional[str] = None,
    working_days: Optional[List[int]] = None,
    global_holidays: Optional[List[str]] = None,
    holidays_by_user: Optional[Dict[str, List[str]]] = None,
) -> dict:
    """Compute expected completion date for a single issue in the current sprint, using the RCPSP-like scheduler.
    Returns {project_key, issue_key, estimated_completion_date, schedule_entry, overall_completion_date}
    """
    sched = schedule_current_sprint_with_dependencies(
        project_key=project_key,
        start_on=start_on,
        working_days=working_days,
        global_holidays=global_holidays,
        holidays_by_user=holidays_by_user,
    )
    per_issue = sched.get("per_issue_schedule", {})
    entry = per_issue.get(issue_key)
    return {
        "project_key": project_key,
        "issue_key": issue_key,
        "estimated_completion_date": entry.get("end") if entry else None,
        "schedule_entry": entry,
        "overall_completion_date": sched.get("overall_completion_date"),
        "sprint_start": sched.get("sprint_start"),
        "sprint_end": sched.get("sprint_end"),
    }


# ------------------------------
# ETA range for a single issue in current sprint (optimistic & pessimistic)
# ------------------------------

def _detect_cycles(nodes: Dict[str, dict]) -> List[List[str]]:
    """Detect cycles in dependency graph defined by nodes mapping with 'dependencies' list.
    Returns a list of cycles, each cycle is a list of node ids in order of encounter.
    """
    color: Dict[str, int] = {k: 0 for k in nodes}  # 0=unvisited,1=visiting,2=done
    stack: List[str] = []
    cycles: List[List[str]] = []

    def dfs(u: str):
        if color[u] == 1:
            # found back-edge; extract cycle from stack
            if u in stack:
                idx = stack.index(u)
                cycles.append(stack[idx:] + [u])
            return
        if color[u] == 2:
            return
        color[u] = 1
        stack.append(u)
        for v in nodes[u].get("dependencies", []):
            if v in nodes:
                dfs(v)
        stack.pop()
        color[u] = 2

    for k in nodes.keys():
        if color[k] == 0:
            dfs(k)
    return cycles


def _topo_order(nodes: Dict[str, dict]) -> List[str]:
    indeg: Dict[str, int] = {k: 0 for k in nodes}
    succ: Dict[str, List[str]] = {k: [] for k in nodes}
    for v, nd in nodes.items():
        for u in nd.get("dependencies", []):
            if u in indeg:
                indeg[v] += 1
                succ[u].append(v)
    from collections import deque
    q = deque([k for k, d in indeg.items() if d == 0])
    order: List[str] = []
    while q:
        u = q.popleft()
        order.append(u)
        for w in succ.get(u, []):
            indeg[w] -= 1
            if indeg[w] == 0:
                q.append(w)
    return order


def _compute_ancestors_of_target(nodes: Dict[str, dict], target: str) -> set:
    # Build reverse graph
    rev: Dict[str, List[str]] = {k: [] for k in nodes}
    for v, nd in nodes.items():
        for u in nd.get("dependencies", []):
            if u in rev:
                rev[v]  # ensure v present
                rev[u].append(v)  # u -> v in forward; reverse: v depends on u, so u has child v
    # Actually we need ancestors: nodes that can reach target; do DFS on reverse edges from target
    parents: Dict[str, List[str]] = {k: [] for k in nodes}
    for v, nd in nodes.items():
        for u in nd.get("dependencies", []):
            if v in parents:
                parents[v].append(u)
    anc: set = set()
    def dfs(u: str):
        for p in parents.get(u, []):
            if p not in anc:
                anc.add(p)
                dfs(p)
    dfs(target)
    return anc


def compute_eta_range_for_issue_current_sprint(
    project_key: str,
    issue_key: str,
    capacity_hours_per_user: Optional[Dict[str, float]] = None,
) -> dict:
    """Compute optimistic and pessimistic ETA (in days) for an issue in the current sprint.
    - Uses story points = 1 day; if capacity_hours_per_user provided (e.g., 6h/day), scales durations by 8/capacity.
    - Detects cycles and returns error if any.
    Returns JSON with schedules and one-line summary.
    """
    graph = current_sprint_dependency_graph(project_key)
    nodes: Dict[str, dict] = graph["nodes"]
    if issue_key not in nodes:
        return {
            "issue": issue_key,
            "error": f"issue not found in current sprint for {project_key}",
        }

    # Apply capacity scaling if provided
    if capacity_hours_per_user:
        for k, nd in nodes.items():
            user = nd.get("assignee") or "UNASSIGNED"
            cap = capacity_hours_per_user.get(user)
            if cap and cap > 0:
                factor = 8.0 / float(cap)
                nd["duration_days"] = int(math.ceil(max(1.0, nd["duration_days"] * factor)))

    # 1) Cycle detection
    cycles = _detect_cycles(nodes)
    if cycles:
        return {
            "issue": issue_key,
            "error": "cycle_detected",
            "cycles": cycles,
        }

    # 2) Optimistic schedule: topo -> earliest start with per-assignee availability
    order = _topo_order(nodes)
    # If order shorter than nodes, graph not a DAG; already checked cycles, but safe-guard
    ES: Dict[str, int] = {k: 0 for k in nodes}
    EF: Dict[str, int] = {k: 0 for k in nodes}
    ass_avail: Dict[str, int] = {}
    backpred: Dict[str, Optional[str]] = {k: None for k in nodes}  # track which dep dominated
    for u in order:
        deps = nodes[u].get("dependencies", [])
        if deps:
            # Pick the dep with max EF
            max_dep = max(deps, key=lambda d: EF.get(d, 0))
            deps_finish = EF.get(max_dep, 0)
        else:
            max_dep = None
            deps_finish = 0
        user = nodes[u].get("assignee") or "UNASSIGNED"
        start_u = max(deps_finish, ass_avail.get(user, 0))
        ES[u] = start_u
        dur = int(max(1, nodes[u].get("duration_days") or 1))
        EF[u] = start_u + dur
        ass_avail[user] = EF[u]
        backpred[u] = max_dep if (deps and EF.get(max_dep, 0) >= ass_avail.get(user, 0)) else (max_dep or None)

    optimistic_days = EF.get(issue_key, 0)
    # Build optimistic critical path by backtracking via max EF predecessors until None or no deps
    crit_path: List[str] = []
    cur = issue_key
    visited_cp = set()
    while cur and cur not in visited_cp:
        crit_path.append(cur)
        visited_cp.add(cur)
        deps = nodes[cur].get("dependencies", [])
        if not deps:
            break
        # choose predecessor with max EF
        prev = max(deps, key=lambda d: EF.get(d, 0))
        if EF.get(prev, -1) <= ES.get(cur, 0):
            cur = prev
        else:
            cur = prev
    crit_path = list(reversed(crit_path))

    # 3) Pessimistic heuristic
    # Precompute ancestors of target
    ancestors = _compute_ancestors_of_target(nodes, issue_key)

    # Build indegree and deps_finish cache
    indeg: Dict[str, int] = {k: 0 for k in nodes}
    succ: Dict[str, List[str]] = {k: [] for k in nodes}
    for v, nd in nodes.items():
        for u in nd.get("dependencies", []):
            if u in indeg:
                indeg[v] += 1
                succ[u].append(v)
    deps_finish_req: Dict[str, int] = {k: 0 for k in nodes}
    ready: set = {k for k, d in indeg.items() if d == 0}
    ass_avail2: Dict[str, int] = {}
    ES2: Dict[str, int] = {}
    EF2: Dict[str, int] = {}
    sched_order: List[str] = []

    def start_time_for(k: str) -> int:
        user = nodes[k].get("assignee") or "UNASSIGNED"
        return max(ass_avail2.get(user, 0), deps_finish_req.get(k, 0))

    while ready:
        # Compute candidate start times
        cands = list(ready)
        starts = {k: start_time_for(k) for k in cands}
        if not starts:
            break
        min_start = min(starts.values())
        # Filter to those with earliest start
        earliest = [k for k in cands if starts[k] == min_start]
        # Prefer non-ancestors of target
        non_anc = [k for k in earliest if k not in ancestors]
        pool = non_anc if non_anc else earliest
        # Pick the longest duration in pool
        def dur_of(k: str) -> int:
            return int(max(1, nodes[k].get("duration_days") or 1))
        chosen = max(pool, key=dur_of)
        # Schedule chosen
        st = starts[chosen]
        ES2[chosen] = st
        d = dur_of(chosen)
        ft = st + d
        EF2[chosen] = ft
        user = nodes[chosen].get("assignee") or "UNASSIGNED"
        ass_avail2[user] = ft
        ready.remove(chosen)
        sched_order.append(chosen)
        # Update successors
        for v in succ.get(chosen, []):
            indeg[v] -= 1
            deps_finish_req[v] = max(deps_finish_req[v], ft)
            if indeg[v] == 0:
                ready.add(v)

    pessimistic_days = EF2.get(issue_key, 0)

    # Prepare schedules arrays
    def to_sched_list(order_list: List[str], ESmap: Dict[str, int], EFmap: Dict[str, int]) -> List[dict]:
        out = []
        for k in order_list:
            out.append({
                "id": k,
                "assignee": nodes[k].get("assignee"),
                "est": ESmap.get(k, 0),
                "eft": EFmap.get(k, ESmap.get(k, 0) + int(max(1, nodes[k].get("duration_days") or 1))),
                "duration": int(max(1, nodes[k].get("duration_days") or 1)),
                "deps": list(nodes[k].get("dependencies", [])),
            })
        return out

    # Build orders: optimistic uses topo order; pessimistic uses sched_order
    optimistic_schedule = to_sched_list(order, ES, EF)
    pessimistic_schedule = to_sched_list(sched_order, ES2, EF2)

    result = {
        "issue": issue_key,
        "optimistic_days": optimistic_days,
        "pessimistic_days": pessimistic_days if pessimistic_days >= optimistic_days else optimistic_days,
        "optimistic_schedule": optimistic_schedule,
        "pessimistic_schedule": pessimistic_schedule,
        "optimistic_critical_path": crit_path,
        "pessimistic_blockers": sorted(list(ancestors)),
        "notes": "Pessimistic schedule biases choices to delay the target by prioritizing non-ancestor ready tasks with longest durations at earliest start times.",
    }
    result["summary"] = (
        f"Expected completion for {issue_key}: "
        f"{result['optimistic_days']}–{result['pessimistic_days']} days (optimistic–pessimistic). See details."
    )
    return result


# ------------------------------
# Dependency graph (for CPA introspection)
# ------------------------------

def build_weighted_dependency_graph(project_key: str) -> dict:
    """Build a directed dependency graph for all issues in a Jira project.
    Nodes are issues with their duration (days). Edges are (dependency -> issue).

    Returns JSON: {"project_key", "nodes": {id: duration}, "edges": [[u, v], ...]}
    """
    issues = _jira_search_project_issues(project_key)
    nodes: Dict[str, float] = {}
    edges: List[Tuple[str, str]] = []
    for iss in issues:
        key = iss.get("key")
        fields = iss.get("fields", {})
        if not key:
            continue
        duration = _get_task_duration(fields)
        # Normalize non-negative float
        try:
            duration = max(0.0, float(duration))
        except Exception:
            duration = 0.0
        nodes[key] = duration
        for dep in _parse_dependencies(fields):
            if dep and dep != key:
                edges.append((dep, key))
    return {"project_key": project_key, "nodes": nodes, "edges": edges}


def format_dependency_graph(graph: dict) -> str:
    """Return a human-readable string for the dependency graph built by
    build_weighted_dependency_graph()."""
    project_key = graph.get("project_key")
    nodes: Dict[str, float] = graph.get("nodes", {})
    edges: List[Tuple[str, str]] = graph.get("edges", [])
    lines: List[str] = []
    lines.append(f"Dependency Graph for project {project_key}")
    lines.append("")
    lines.append("Nodes (duration in days):")
    for k in sorted(nodes.keys(), key=lambda s: (s.split('-')[0] if isinstance(s, str) else '',
                                                 int(s.rsplit('-', 1)[1]) if isinstance(s, str) and '-' in s and s.rsplit('-', 1)[1].isdigit() else 0,
                                                 s)):
        lines.append(f" - {k}: {nodes[k]:.2f}")
    lines.append("")
    lines.append("Edges (dependency -> issue):")
    if edges:
        # Sort edges deterministically by numeric part where possible
        def _num(x: str) -> int:
            try:
                return int(x.rsplit('-', 1)[1]) if '-' in x else 0
            except Exception:
                return 0
        for u, v in sorted(edges, key=lambda e: (_num(e[0]), e[0], _num(e[1]), e[1])):
            lines.append(f" - {u} -> {v}")
    else:
        lines.append(" - (no dependencies detected)")
    return "\n".join(lines)


def print_dependency_graph_for_issue(issue_key: str) -> str:
    """Convenience helper: infer project_key from an issue key like 'TEST-123',
    build the dependency graph for the whole project, and return a printable string.
    The caller may print the returned string; this function also prints it for convenience.
    """
    if not issue_key or '-' not in issue_key:
        raise ValueError("issue_key must look like 'PROJ-123'")
    project_key = issue_key.split('-', 1)[0]
    graph = build_weighted_dependency_graph(project_key)
    text = format_dependency_graph(graph)
    # Print for quick inspection in agent logs
    try:
        print(text)
    except Exception:
        pass
    return text
