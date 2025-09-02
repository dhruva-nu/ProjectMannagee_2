from typing import Dict, List, Tuple
from backend.app.db.models import ProjectModel


def _topo_sort(nodes: List[str], edges: Dict[str, List[str]]) -> List[str]:
    from collections import deque
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


def run_cpa_calc(project: ProjectModel) -> dict:
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
    # Critical path: tasks with zero slack; build ordered path by filtering order
    crit_set = {u for u in nodes if abs(slack[u]) < 1e-9}
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
