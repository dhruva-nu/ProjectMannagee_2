from typing import Dict, List, Tuple

from .jira import _jira_search_project_issues, _get_task_duration, _parse_dependencies

def build_weighted_dependency_graph(project_key: str) -> dict:
    """Build a directed dependency graph for all issues in a Jira project.
    Nodes are issues with their duration (days). Edges are (dependency -> issue).

    Returns JSON: {"project_key", "nodes": {id: duration}, "edges": [[u, v], ...]}`
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
