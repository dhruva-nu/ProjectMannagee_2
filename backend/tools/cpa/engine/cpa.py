from typing import Dict, List, Tuple, Optional
import heapq
import math
from sqlalchemy import text

try:
    # When running inside backend/ (e.g., uvicorn main:app)
    from app.db.database import SessionLocal
    from app.db.db_loader import load_project_from_db
    from app.db.models import ProjectModel
except ModuleNotFoundError:
    # When importing as backend.* from project root
    from backend.app.db.database import SessionLocal
    from backend.app.db.db_loader import load_project_from_db
    from backend.app.db.models import ProjectModel

from .jira import refresh_from_jira

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


essential_keys = ["id", "ES", "EF", "LS", "LF", "slack", "duration", "isCritical"] # Essential keys for CPA


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
    ref = refresh_sprint_from_jira(project_key)
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
