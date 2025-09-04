from typing import Dict, List, Optional
import math

from .sprint_dependency import current_sprint_dependency_graph

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
