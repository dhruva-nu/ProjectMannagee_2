#!/usr/bin/env python3
"""
Git commit-msg hook handler:
- Looks for pattern "--issue <ISSUE_KEY>" in the commit message
- Transitions the referenced Jira issue(s) to "In Review"

Usage (invoked by Git commit-msg hook):
  commit_msg_hook.py <path_to_commit_message_file>

Requirements:
- JIRA env vars configured in backend/.env or environment:
  - JIRA_SERVER
  - JIRA_USERNAME
  - JIRA_API
- Python deps: requests, python-dotenv

This script intentionally does not use any LLMs.
"""
import re
import sys
from pathlib import Path

# Allow running from repo root or any directory
REPO_ROOT = Path(__file__).resolve().parents[4]  # .../ProjectMannagee_2
BACKEND_ROOT = REPO_ROOT / "backend"

# Ensure backend is importable
sys.path.insert(0, str(BACKEND_ROOT))

from tools.jira.cpa_tools import transition_issue_status  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

ISSUE_PATTERN = re.compile(r"--issue\s+([A-Z][A-Z0-9]+-\d+)(?:\s+(--toProgress|--toDone))?")

STATUS_MAP = {
    None: "In Review",
    "--toProgress": "In Progress",
    "--toDone": "Done",
}

def parse_issue_keys(message: str) -> list[tuple[str, str]]:
    issues_with_status: list[tuple[str, str]] = []
    for m in ISSUE_PATTERN.finditer(message):
        issue_key = m.group(1)
        status_flag = m.group(2) # This will be '--toProgress', '--toDone', or None
        target_status = STATUS_MAP.get(status_flag, "In Review") # Default to In Review if flag is not recognized or not present
        issues_with_status.append((issue_key, target_status))

    # de-duplicate while preserving order, prioritizing later flags for the same issue
    # A dictionary can handle this naturally.
    deduplicated_issues = {}
    for key, status in issues_with_status:
        deduplicated_issues[key] = status

    return list(deduplicated_issues.items())


def main() -> int:
    if len(sys.argv) < 2:
        print("commit_msg_hook.py: missing commit message file path", file=sys.stderr)
        return 2

    # Load backend/.env explicitly so Jira credentials are available
    try:
        load_dotenv(REPO_ROOT / "backend" / ".env")
    except Exception:
        # Non-fatal; environment may already be configured
        pass

    commit_msg_path = Path(sys.argv[1])
    try:
        content = commit_msg_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"commit_msg_hook.py: failed reading commit message: {e}", file=sys.stderr)
        return 2

    issue_keys = parse_issue_keys(content)
    if not issue_keys:
        # Nothing to do; allow commit
        return 0

    # For each referenced issue, transition to In Review
    failures: list[str] = []
    for key in issue_keys:
        try:
            result = transition_issue_status(key, "In Review")
            # transition_issue_status returns a message string; log it to stderr so commit output shows it
            print(result, file=sys.stderr)
            if not result.lower().startswith("successfully"):
                failures.append(key)
        except Exception as e:
            print(f"Error transitioning {key}: {e}", file=sys.stderr)
            failures.append(key)

    # Do not block the commit if Jira transition fails; just warn
    if failures:
        print(
            "Warning: Jira transition failed for: " + ", ".join(failures) +
            ". Commit proceeded; you may need to transition manually.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
