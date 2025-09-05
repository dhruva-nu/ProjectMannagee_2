import json
from logging import log
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth


def load_tech_stack_info():
    """Loads the tech stack information from docs/tech_stack.json."""
    try:
        with open("docs/tech_stack.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        print("Error decoding tech_stack.json. Please check its format.")
        return None


def _jira_env():
    jira_server = os.getenv("JIRA_SERVER")
    jira_username = os.getenv("JIRA_USERNAME")
    jira_api_token = os.getenv("JIRA_API")
    if not all([jira_server, jira_username, jira_api_token]):
        raise ValueError(
            "Error: Jira environment variables (JIRA_SERVER, JIRA_USERNAME, JIRA_API) are not set."
        )
    return jira_server, jira_username, jira_api_token


def _sp_field_key() -> str | None:
    """Return the Jira custom field key for Story Points, e.g., 'customfield_10016'. Config via JIRA_STORY_POINTS_FIELD."""
    key = os.getenv("JIRA_STORY_POINTS_FIELD")
    # Fallback to a common default if not configured. This is the default SP field in many Jira Cloud instances.
    # If your instance uses a different key, set JIRA_STORY_POINTS_FIELD in backend/.env.
    return key or "customfield_10016"


def _fetch_issue_details(issue_key: str) -> dict | None:
    """Internal: fetch detailed information for a specific Jira issue."""
    jira_server, jira_username, jira_api_token = _jira_env()
    auth = HTTPBasicAuth(jira_username, jira_api_token)
    headers = {"Accept": "application/json"}
    issue_url = f"{jira_server}/rest/api/2/issue/{issue_key}?fields=summary,status,assignee,reporter,priority,issuetype,created,updated,duedate,resolutiondate,description,comment,labels,components,fixVersions,issuelinks"
    response = requests.get(issue_url, headers=headers, auth=auth).json()
    if response.get("errorMessages") or response.get("errors"):
        return None
    fields = response.get("fields", {})
    # Parse blockers from issue links (standard Jira link type "Blocks")
    blockers: list[dict] = []
    for link in fields.get("issuelinks", []) or []:
        link_type = (link.get("type") or {})
        inward_desc = (link_type.get("inward") or "").lower()
        type_name = (link_type.get("name") or "").lower()
        # An issue is considered blocked by inwardIssue when type is Blocks/Dependency and inward reads like "is blocked by"
        inward_issue = link.get("inwardIssue")
        if inward_issue and (
            "blocked" in inward_desc or type_name in {"blocks", "dependency", "depends"}
        ):
            blockers.append({
                "key": inward_issue.get("key"),
                "summary": (inward_issue.get("fields") or {}).get("summary"),
            })
    assignee_data = fields.get("assignee", {})
    return {
        "key": response.get("key"),
        "summary": fields.get("summary"),
        "status": fields.get("status", {}).get("name"),
        "assignee": {
            "displayName": assignee_data.get("displayName"),
            "emailAddress": assignee_data.get("emailAddress"),
            "avatarUrls": assignee_data.get("avatarUrls"),
        } if assignee_data else None,
        "reporter": fields.get("reporter", {}).get("displayName") if fields.get("reporter") else None,
        "priority": fields.get("priority", {}).get("name"),
        "issue_type": fields.get("issuetype", {}).get("name"),
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "duedate": fields.get("duedate"),
        "resolutiondate": fields.get("resolutiondate"),
        "description": fields.get("description"),
        "comments": [comment.get("body") for comment in fields.get("comment", {}).get("comments", [])],
        "labels": fields.get("labels", []),
        "components": [comp.get("name") for comp in fields.get("components", [])],
        "fix_versions": [fv.get("name") for fv in fields.get("fixVersions", [])],
        "blockers": blockers,
        "custom_fields": {k: v for k, v in fields.items() if k.startswith('customfield_')}
    }


def _fetch_active_sprint_issues(project_key: str, max_results: int = 50) -> dict | None:
    """Returns { 'sprint': {...}, 'issues': [ {key, summary, status, statusCategory, assignee, story_points} ] } for the active sprint."""
    jira_server, jira_username, jira_api_token = _jira_env()
    auth = HTTPBasicAuth(jira_username, jira_api_token)
    headers = {"Accept": "application/json"}
    boards_url = f"{jira_server}/rest/agile/1.0/board?projectKeyOrId={project_key}"
    boards = requests.get(boards_url, headers=headers, auth=auth).json()
    if not boards.get("values"):
        return None
    board_id = boards["values"][0]["id"]
    sprints_url = f"{jira_server}/rest/agile/1.0/board/{board_id}/sprint?state=active"
    sprints = requests.get(sprints_url, headers=headers, auth=auth).json()
    if not sprints.get("values"):
        return None
    sprint = sprints["values"][0]
    sprint_info = {
        "id": sprint["id"],
        "name": sprint["name"],
        "startDate": sprint.get("startDate"),
        "endDate": sprint.get("endDate"),
    }
    issues_url = f"{jira_server}/rest/agile/1.0/sprint/{sprint_info['id']}/issue"
    all_issues = []
    start_at = 0
    while True:
        params = {"startAt": start_at, "maxResults": max_results}
        resp = requests.get(issues_url, headers=headers, auth=auth, params=params).json()
        issues = resp.get("issues", [])
        all_issues.extend(issues)
        if start_at + max_results >= resp.get("total", 0):
            break
        start_at += max_results
    sp_key = _sp_field_key()
    simplified = []
    for issue in all_issues:
        fields = issue.get("fields", {})
        status_obj = fields.get("status") or {}
        status_category = (status_obj.get("statusCategory") or {}).get("key")  # e.g., 'new', 'indeterminate', 'done'
        story_points = None
        if sp_key and sp_key in fields:
            sp_val = fields.get(sp_key)
            # Ensure numeric if possible
            try:
                story_points = float(sp_val) if sp_val is not None else None
            except (TypeError, ValueError):
                story_points = None
        simplified.append({
            "key": issue.get("key"),
            "summary": fields.get("summary"),
            "status": status_obj.get("name"),
            "statusCategory": status_category,
            "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
            "story_points": story_points,
        })
    return {"sprint": sprint_info, "issues": simplified}


def answer_jira_query(issue_key: str, query: str) -> str:
    """
    Use Gemini ADK (gemini-2.0-flash) to answer questions about a Jira issue
    using its details and optional project knowledge base as context.
    """
    load_dotenv()

    issue_details = _fetch_issue_details(issue_key)
    tech_stack_info = load_tech_stack_info()

    if not issue_details:
        return f"Could not find details for Jira issue {issue_key}. Please check the issue key."

    # Prepare concise, structured context for the LLM
    status = issue_details.get("status", "Unknown")
    summary = issue_details.get("summary", "No summary available")
    assignee = issue_details.get("assignee", "unassigned")
    due_date = issue_details.get("duedate")
    resolution_date = issue_details.get("resolutiondate")
    labels = issue_details.get("labels", [])
    comments = issue_details.get("comments", [])
    blockers = issue_details.get("blockers", [])

    last_comments = comments[-3:] if comments else []
    tech_notes = tech_stack_info.get("cpa_relevant_info", {}) if tech_stack_info else {}

    # We intentionally do not import ADK Agent here to keep this a pure tool
    # The orchestrating agent should wrap this tool in a FunctionTool and provide the LLM
    context_blob = {
        "issue_key": issue_key,
        "summary": summary,
        "status": status,
        "assignee": assignee,
        "due_date": due_date,
        "resolution_date": resolution_date,
        "labels": labels,
        "last_comments": last_comments,
        "blockers": blockers,
        "tech_notes": tech_notes,
    }

    # Produce a deterministic, concise answer based on available context
    lines = [
        f"Issue {issue_key}: '{summary}' | Status: {status} | Assignee: {assignee}",
    ]
    if resolution_date:
        lines.append(f"Resolved on {resolution_date}.")
    elif due_date:
        lines.append(f"Due date: {due_date}.")
    if blockers:
        lines.append("Blocking issues:")
        for b in blockers:
            lines.append(f"- {b.get('key')}: {b.get('summary')}")
    if last_comments:
        lines.append("Recent comments:")
        for i, c in enumerate(last_comments, 1):
            lines.append(f"- {i}. {c}")
    lines.append(f"Question: {query}")
    lines.append("Note: This answer uses deterministic context only. An LLM-enabled agent can enrich this.")
    return "\n".join(lines)


def what_is_blocking(issue_key: str) -> str:
    """
    Returns a human-readable list of blocking issues for the given Jira issue.
    This does not rely on the LLM and queries Jira issue links.
    """
    load_dotenv()
    try:
        details = _fetch_issue_details(issue_key)
        if not details:
            return f"Could not find details for Jira issue {issue_key}."
        blockers = details.get("blockers", []) or []
        if not blockers:
            return f"No explicit blockers found for {issue_key}."
        lines = [f"Blockers for {issue_key}:"]
        for b in blockers:
            lines.append(f"- {b.get('key')}: {b.get('summary')}")
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to fetch blockers for {issue_key}: {e}"


def answer_sprint_hypothetical(project_key: str, issue_key: str, query: str) -> str:
    """
    Answers hypothetical sprint planning questions like moving an issue to the next sprint.
    Provides sprint info, remaining issues after excluding the given issue, and assignee breakdown.
    """
    load_dotenv()
    data = _fetch_active_sprint_issues(project_key)
    if not data:
        return f"No active sprint found for project {project_key}."
    sprint = data.get("sprint") or {}
    issues = data.get("issues") or []
    remaining = [it for it in issues if it.get("key") != issue_key]
    by_status: dict[str, int] = {}
    by_assignee: dict[str, int] = {}
    # Math: compute SP totals and burn-rate based projection
    total_sp = sum((it.get("story_points") or 0.0) for it in issues)
    removed_sp = next((it.get("story_points") or 0.0 for it in issues if it.get("key") == issue_key), 0.0)
    remaining_sp = sum((it.get("story_points") or 0.0) for it in remaining)
    # Completed so far = SP in items whose statusCategory == 'done'
    completed_sp = sum((it.get("story_points") or 0.0) for it in issues if (it.get("statusCategory") == "done"))
    # Dates
    start_str = sprint.get("startDate")
    end_str = sprint.get("endDate")
    today = datetime.utcnow()

    def _parse_date(s: str | None):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None

    start_dt = _parse_date(start_str)
    end_dt = _parse_date(end_str)
    # Burn rate in SP/day
    if start_dt:
        days_elapsed = max((today - start_dt).days, 1)
    else:
        days_elapsed = 1
    burn_rate = completed_sp / days_elapsed if days_elapsed > 0 else 0.0
    # Projected days to finish remaining SP
    projected_days = None
    if burn_rate > 0:
        projected_days = remaining_sp / burn_rate
    # Build breakdowns
    for it in remaining:
        st = it.get("status") or "Unknown"
        by_status[st] = by_status.get(st, 0) + 1
        asg = it.get("assignee") or "Unassigned"
        by_assignee[asg] = by_assignee.get(asg, 0) + 1

    lines = [f"Sprint: {sprint.get('name')} (start: {start_str}, end: {end_str})."]
    lines.append(f"Removed issue: {issue_key} (SP: {removed_sp}).")
    lines.append(
        f"Remaining issues: {len(remaining)} | Remaining SP: {remaining_sp:.2f} | Completed SP: {completed_sp:.2f}."
    )
    lines.append(
        "By status: "
        + (", ".join(f"{k}: {v}" for k, v in by_status.items()) if by_status else "none")
    )
    lines.append(
        "By assignee: "
        + (", ".join(f"{k}: {v}" for k, v in by_assignee.items()) if by_assignee else "none")
    )
    if burn_rate > 0 and projected_days is not None:
        projected_completion = today + timedelta(days=max(projected_days, 0))
        lines.append(
            f"Burn rate: {burn_rate:.2f} SP/day | Projected completion: {projected_completion.date().isoformat()}."
        )
        if end_dt:
            lines.append("Within sprint: " + ("YES" if projected_completion <= end_dt else "NO"))
    else:
        lines.append("Insufficient data to compute burn rate (no completed SP or missing SP field).")
    # Add user's hypothetical question for traceability
    lines.append(f"Question: {query}")
    return "\n".join(lines)


def who_is_assigned(issue_key: str) -> dict:
    """Return assignee info in a stable shape expected by callers/tests.

    Success shape:
    {"issue_key": KEY, "assignee": {"name": str, "email": str, "avatarUrl": str|None, "accountId": str|None}}
    Unassigned:
    {"issue_key": KEY, "assignee": None}
    Error:
    {"error": str}
    """
    # Basic validation
    if not issue_key or not isinstance(issue_key, str) or "-" not in issue_key:
        return {"error": "Invalid issue key"}
    try:
        details = _fetch_issue_details(issue_key)
        if not details:
            return {"error": f"Jira issue {issue_key} not found."}
        assignee_data = details.get("assignee")
        if not assignee_data or not assignee_data.get("displayName"):
            return {"issue_key": issue_key, "assignee": None}

        display_name = assignee_data.get("displayName")
        email_address = assignee_data.get("emailAddress")
        avatar_urls = assignee_data.get("avatarUrls")
        account_id = assignee_data.get("accountId")

        avatar_url = None
        if avatar_urls:
            avatar_url = (
                avatar_urls.get("48x48")
                or avatar_urls.get("32x32")
                or next(iter(avatar_urls.values()), None)
            )
        return {
            "issue_key": issue_key,
            "assignee": {
                "name": display_name,
                "email": email_address,
                "avatarUrl": avatar_url,
                "accountId": account_id,
            },
        }
    except requests.exceptions.Timeout:
        return {"error": "Request timeout while fetching assignee information"}
    except requests.exceptions.RequestException as e:
        return {"error": f"Network error while fetching assignee information: {e}"}
    except ValueError as e:
        # Likely missing environment variables from _jira_env
        return {"error": f"Jira environment variables missing or invalid: {e}"}
    except Exception as e:
        return {"error": str(e)}

def transition_issue_status(issue_key: str, new_status: str) -> str:
    """
    Transitions the status of a Jira issue to the specified new status.

    Args:
        issue_key: The key of the Jira issue (e.g., "PROJ-123").
        new_status: The target status name (e.g., "Done", "In Progress").

    Returns:
        A message indicating the success or failure of the transition.
    """
    load_dotenv()
    jira_server, jira_username, jira_api_token = _jira_env()
    auth = HTTPBasicAuth(jira_username, jira_api_token)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    # 1. Get available transitions for the issue
    transitions_url = f"{jira_server}/rest/api/2/issue/{issue_key}/transitions"
    response = requests.get(transitions_url, headers=headers, auth=auth).json()

    if response.get("errorMessages"):
        return f"Error fetching transitions for {issue_key}: {response.get('errorMessages')}"

    transitions = response.get("transitions", [])
    transition_id = None
    for t in transitions:
        if t.get("name").lower() == new_status.lower():
            transition_id = t.get("id")
            break

    if not transition_id:
        available_statuses = ", ".join([t.get("name") for t in transitions])
        return f"Status '{new_status}' is not a valid transition for {issue_key}. Available transitions: {available_statuses or 'None'}."

    # 2. Execute the transition
    transition_url = f"{jira_server}/rest/api/2/issue/{issue_key}/transitions"
    payload = {
        "transition": {
            "id": transition_id
        }
    }
    response = requests.post(transition_url, headers=headers, auth=auth, data=json.dumps(payload))

    if response.status_code == 204: # 204 No Content indicates success
        return f"Successfully transitioned issue {issue_key} to status '{new_status}'."
    else:
        error_message = response.json().get("errorMessages", response.text)
        return f"Failed to transition issue {issue_key} to '{new_status}': {error_message}"

def add_comment_to_issue(issue_key: str, comment_body: str) -> str:
    """
    Adds a comment to a specified Jira issue.

    Args:
        issue_key: The key of the Jira issue (e.g., "PROJ-123").
        comment_body: The content of the comment to add.

    Returns:
        A message indicating the success or failure of adding the comment.
    """
    load_dotenv()
    jira_server, jira_username, jira_api_token = _jira_env()
    auth = HTTPBasicAuth(jira_username, jira_api_token)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    comment_url = f"{jira_server}/rest/api/2/issue/{issue_key}/comment"
    payload = {
        "body": comment_body
    }
    response = requests.post(comment_url, headers=headers, auth=auth, data=json.dumps(payload))

    if response.status_code == 201: # 201 Created indicates success
        return f"Successfully added comment to issue {issue_key}."
    else:
        error_message = response.json().get("errorMessages", response.text)
        return f"Failed to add comment to issue {issue_key}: {error_message}"


def print_issue_dependency_graph(issue_key: str) -> str:
    """Build and print a directed weighted dependency graph for the issue's project.
    This is intended to be called when asked questions like
    "when can I expect issue TESTPROJ-23 to be complete". For now, it only
    builds and prints the graph for CPA readiness.

    Returns the textual graph representation as well, for use in UIs.
    """
    # Local import to avoid circular dependency: engine imports helpers from this module
    try:
        from tools.cpa.engine import print_current_sprint_dependency_graph_for_issue as _print_graph
    except ModuleNotFoundError:
        from backend.tools.cpa.engine import print_current_sprint_dependency_graph_for_issue as _print_graph
    return _print_graph(issue_key)


def answer_when_issue_complete_range(issue_key: str,
                                     capacity_hours_per_user: dict | None = None,
                                     workdays: bool = True) -> dict:
    """Return full JSON ETA range for the current sprint (optimistic–pessimistic) for the given issue.

    Parameters:
    - capacity_hours_per_user: optional mapping like {"alice": 6} to scale durations (8h baseline)
    - workdays: if True, values are in working days; if False, they are approximated calendar days
    """
    if not issue_key or '-' not in issue_key:
        return {"error": "Please provide a valid Jira issue key, e.g., TESTPROJ-23."}
    project_key = issue_key.split('-', 1)[0]
    # Local import to avoid circular dependency
    try:
        from tools.cpa.engine import compute_eta_range_for_issue_current_sprint as _eta_range
    except ModuleNotFoundError:
        from backend.tools.cpa.engine import compute_eta_range_for_issue_current_sprint as _eta_range

    result = _eta_range(project_key, issue_key, capacity_hours_per_user)
    if "error" in result:
        return result
    result["human"] = f"Expected completion for {issue_key}: {result['optimistic_days']}–{result['pessimistic_days']} days (optimistic–pessimistic). See details."
    result["workdays"] = workdays
    return result


def answer_when_issue_complete(issue_key: str,
                               capacity_hours_per_user: dict | None = None,
                               workdays: bool = True) -> str:
    """Return a one-line human answer with best and worst case in days for the given issue.
    Example: "Expected completion for TESTPROJ-25: 4–7 days (optimistic–pessimistic). See details."
    """
    res = answer_when_issue_complete_range(issue_key, capacity_hours_per_user, workdays)
    if isinstance(res, dict) and "error" in res:
        return res.get("error") or "Could not estimate completion."
    return res.get("human", "Could not estimate completion.")

