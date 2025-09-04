from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Set
import math

try:
    from tools.jira.cpa_tools import _sp_field_key
except ModuleNotFoundError:
    from backend.tools.jira.cpa_tools import _sp_field_key

from .jira import _cached_current_sprint_issues, _extract_sprint_dates, _get_task_duration, _parse_iso_date


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


def _next_working_day(d: date, working_days: Set[int], holidays: Set[date]) -> date:
    """Return the same date if it is a working day (and not a holiday), otherwise the next working day."""
    cur = d
    while True:
        if cur.weekday() in working_days and cur not in holidays:
            return cur
        cur = cur + timedelta(days=1)


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
    - working_days: weekdays considered working (0=Mon..6=Sun). Default: weekdays (Mon–Fri).
    - global_holidays: list of ISO dates treated as non-working for all.
    - holidays_by_user: mapping of user displayName -> list of ISO dates of unavailability.
    """
    issues = _cached_current_sprint_issues(project_key)

    # Determine start date
    sprint_start, sprint_end = _extract_sprint_dates(issues)
    start_dt = _parse_iso_date(start_on) if start_on else None
    base_start = sprint_start or start_dt or datetime.utcnow().date()

    # Working calendar (default to weekdays Mon-Fri)
    working_days_set: Set[int] = set(working_days) if working_days is not None else {0,1,2,3,4}
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
            # Align start to next working day for this user
            start_d = _next_working_day(current, working_days_set, user_holidays)
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


def sprint_completion_if_issue_removed(
    project_key: str,
    removed_issue_key: str,
    start_on: Optional[str] = None,
    working_days: Optional[List[int]] = None,
    global_holidays: Optional[List[str]] = None,
    holidays_by_user: Optional[Dict[str, List[str]]] = None,
) -> dict:
    """
    Simulate the overall sprint completion date if a given issue is removed from the current sprint.

    Returns a JSON with before/after overall completion ISO dates and delta_days (positive means earlier finish).
    """
    # Baseline timeline (with all issues)
    baseline = current_sprint_cpa_timeline(
        project_key=project_key,
        start_on=start_on,
        working_days=working_days,
        global_holidays=global_holidays,
        holidays_by_user=holidays_by_user,
    )

    # Fetch all issues once and filter out the removed issue, then recompute timelines per user with the same logic
    issues = _cached_current_sprint_issues(project_key)

    # Determine start date
    sprint_start, sprint_end = _extract_sprint_dates(issues)
    start_dt = _parse_iso_date(start_on) if start_on else None
    base_start = sprint_start or start_dt or datetime.utcnow().date()

    # Working calendar (default to weekdays Mon-Fri)
    working_days_set: Set[int] = set(working_days) if working_days is not None else {0,1,2,3,4}
    global_hols_set: Set[date] = _to_date_set(global_holidays)

    # Prepare per-assignee queues excluding the removed issue
    sp_key = _sp_field_key()
    items: List[dict] = []
    for iss in issues:
        key = iss.get("key")
        if key == removed_issue_key:
            continue
        fields = iss.get("fields", {})
        assignee = (fields.get("assignee") or {}).get("displayName") if fields.get("assignee") else "Unassigned"
        duration_days = _get_task_duration(fields)
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

    def _issue_key_number(k: Optional[str]) -> int:
        try:
            if not k or '-' not in k:
                return 0
            return int(k.rsplit('-', 1)[1])
        except Exception:
            return 0

    schedules: Dict[str, List[dict]] = {}
    for user, tasks in by_user.items():
        tasks = sorted(tasks, key=lambda t: (_issue_key_number(t.get("key")), t.get("key") or ""))
        user_holidays = _to_date_set((holidays_by_user or {}).get(user)) | global_hols_set
        current = base_start
        user_sched: List[dict] = []
        for t in tasks:
            start_d = _next_working_day(current, working_days_set, user_holidays)
            end_d = _advance_working_days(start_d, t["estimated_days"], working_days_set, user_holidays)
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
        schedules[user] = user_sched

    # Overall completion after removal
    all_ends: List[date] = []
    for user, sched in schedules.items():
        for e in sched:
            all_ends.append(_parse_iso_date(e["end"]))
    new_overall_end = max([d for d in all_ends if d is not None], default=base_start)

    before_date = baseline.get("overall_completion_date")
    after_date = new_overall_end.isoformat()

    # Compute delta in days (before - after)
    delta_days = None
    try:
        if before_date:
            bd = _parse_iso_date(before_date)
            ad = _parse_iso_date(after_date)
            if bd and ad:
                delta_days = (bd - ad).days
    except Exception:
        delta_days = None

    return {
        "project_key": project_key,
        "removed_issue": removed_issue_key,
        "sprint_start": (sprint_start or base_start).isoformat() if (sprint_start or base_start) else None,
        "sprint_end": sprint_end.isoformat() if sprint_end else None,
        "before_overall_completion_date": before_date,
        "after_overall_completion_date": after_date,
        "delta_days": delta_days,
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

    # Working calendar (default to weekdays Mon-Fri)
    working_days_set: Set[int] = set(working_days) if working_days is not None else {0,1,2,3,4}
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
        sdt = _next_working_day(current, working_days_set, user_holidays)
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
