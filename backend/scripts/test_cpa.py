import json
from backend.tools.cpa.engine_tools import (
    refresh_from_jira,
    run_cpa,
    get_critical_path,
    get_task_slack,
    get_project_duration,
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


if __name__ == "__main__":
    main()
