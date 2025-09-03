import os
import json
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional, Set
import math

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
from tools.jira.cpa_tools import _jira_env, _sp_field_key
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
