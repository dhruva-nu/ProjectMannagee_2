from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional, Set
import math
import heapq

try:
    from tools.jira.cpa_tools import _sp_field_key
except ModuleNotFoundError:
    from backend.tools.jira.cpa_tools import _sp_field_key

from .jira import _cached_current_sprint_issues, _get_task_duration, _parse_dependencies, _parse_iso_date, _extract_sprint_dates
from .sprint_timeline import _advance_working_days, _to_date_set

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

def _date_after(d: date, days: int) -> date:
    return d + timedelta(days=days)


def _max_date(a: Optional[date], b: Optional[date]) -> Optional[date]:
    if a is None:
        return b
    if b is None:
        return a
    return a if a >= b else b

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
