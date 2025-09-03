import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from backend.tools.cpa.engine_tools import (
    refresh_from_jira,
    run_cpa,
    get_critical_path,
    get_task_slack,
    get_project_duration,
    current_sprint_cpa_timeline,
    estimate_issue_completion_in_current_sprint,
)

PROJECT_KEY = "TESTPROJ"
TASKS = ["TESTPROJ-15", "TESTPROJ-16", "TESTPROJ-17", "TESTPROJ-18"]


def main():
    print("=== refresh_from_jira ===")
    ref = refresh_from_jira(PROJECT_KEY)
    print(json.dumps(ref, indent=2))

    pid = ref.get("project_id")
    if not pid:
        raise SystemExit("No project_id returned from refresh_from_jira")

    print("\n=== run_cpa ===")
    cpa = run_cpa(pid)
    print(json.dumps(cpa, indent=2))

    print("\n=== get_critical_path ===")
    crit = get_critical_path(pid)
    print(json.dumps(crit, indent=2))

    print("\n=== get_task_slack (each) ===")
    for t in TASKS:
        s = get_task_slack(t)
        print(json.dumps(s, indent=2))

    print("\n=== get_project_duration ===")
    dur = get_project_duration(pid)
    print(json.dumps(dur, indent=2))

    print("\n=== current_sprint_cpa_timeline ===")
    sprint = current_sprint_cpa_timeline(PROJECT_KEY)
    print(json.dumps(sprint, indent=2))

    target = TASKS[-1]
    print("\n=== estimate_issue_completion_in_current_sprint ===")
    eta = estimate_issue_completion_in_current_sprint(PROJECT_KEY, target)
    print(json.dumps(eta, indent=2))


if __name__ == "__main__":
    main()
