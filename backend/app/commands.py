
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple, Optional
import requests
try:
    from tools.github.repo_tools import list_todays_commits
except ModuleNotFoundError:
    from backend.tools.github.repo_tools import list_todays_commits

def _extract_jira_key(text: str) -> str | None:
    """
    Extract a plausible Jira key like ABC-123 from free-form text without regex.
    Algorithm: scan characters; find a run starting with a letter, followed by alnum,
    then a single '-', then one or more digits. Return the first match in UPPERCASE.
    """
    if not text:
        return None
    s = text
    n = len(s)
    i = 0
    while i < n:
        ch = s[i]
        if ch.isalpha():
            prev_ok = i == 0 or (not s[i-1].isalnum() and s[i-1] != '_')
            if not prev_ok:
                i += 1
                continue
            # collect project key (letters/digits), must start with this letter
            j = i + 1
            while j < n and s[j].isalnum():
                j += 1
            # need a hyphen next
            if j < n and s[j] == '-':
                k = j + 1
                # collect digits
                start_digits = k
                while k < n and s[k].isdigit():
                    k += 1
                if k > start_digits:  # at least one digit
                    left = s[i:j]
                    right = s[start_digits:k]
                    # ensure next char is a boundary (not alnum)
                    next_ok = k >= n or (not s[k].isalnum())
                    if next_ok:
                        return f"{left.upper()}-{right}"
            # move to next position after i to continue search
        i += 1
    return None

# ------- helpers: parsing & state -------
def _has_flag(text: str, variants: list[str]) -> bool:
    if not text:
        return False
    tl = text.lower()
    # normalize multiple spaces
    tl = " ".join(tl.split())
    for v in variants:
        if v in tl:
            return True
    return False

def _parse_repo_branch(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse repo and branch from free text without regex.
    Supported forms:
    - repo=owner/name or repository=owner/name
    - --repo owner/name
    - branch=name or --branch name
    - fallback: first token containing one '/' that looks like owner/repo
    """
    if not text:
        return None, None
    tokens = text.strip().split()
    repo = None
    branch = None
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        low = tok.lower()
        if "=" in tok:
            k, v = tok.split("=", 1)
            k = k.strip().lower()
            v = v.strip()
            if k in ("repo", "repository") and "/" in v:
                repo = v
            elif k == "branch" and v:
                branch = v
        elif low == "--repo" and (i + 1) < len(tokens):
            nxt = tokens[i + 1].strip()
            if "/" in nxt:
                repo = nxt
            i += 1
        elif low == "--branch" and (i + 1) < len(tokens):
            branch = tokens[i + 1].strip()
            i += 1
        else:
            # fallback: owner/repo looking token
            if "/" in tok and repo is None:
                left, right = tok.split("/", 1)
                if left and right:
                    repo = tok
        i += 1
    return repo, branch

def _state_file_path() -> Path:
    return Path(__file__).parent / ".workday_state.json"

def _save_workday_start(start_iso: str, repo: Optional[str], branch: Optional[str]) -> None:
    data = {"start": start_iso}
    if repo:
        data["repo"] = repo
    if branch:
        data["branch"] = branch
    _state_file_path().write_text(json.dumps(data, indent=2))

def _load_workday_start() -> dict | None:
    p = _state_file_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None

# ------- helpers: GitHub & Jira -------
def _github_commits_since(repo_full_name: str, start_dt_local: datetime, branch: Optional[str] = None) -> str:
    """
    List commits between start_dt_local (inclusive) and now (exclusive) for a repo.
    Fallbacks to token/env already loaded by main.
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        return "Error: GitHub environment variable (GITHUB_TOKEN) is not set."
    now_local = datetime.now().astimezone()
    since_utc = start_dt_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    until_utc = now_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {github_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    params = {"since": since_utc, "until": until_utc, "per_page": 100}
    if branch:
        params["sha"] = branch
    try:
        url = f"https://api.github.com/repos/{repo_full_name}/commits"
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        commits = resp.json()
        if not isinstance(commits, list) or not commits:
            return f"No commits found for {repo_full_name} since {start_dt_local.strftime('%Y-%m-%d %H:%M')} (local)."
        lines = [
            f"Commits for {repo_full_name} since {start_dt_local.strftime('%Y-%m-%d %H:%M')} (local):"
        ]
        for c in commits:
            sha = (c.get("sha") or "")[:7]
            commit = c.get("commit", {})
            msg = (commit.get("message") or "").splitlines()[0]
            author = commit.get("author", {})
            author_name = author.get("name") or "unknown"
            author_date_str = author.get("date")
            t_local = author_date_str or "--:--"
            try:
                if author_date_str:
                    dt_utc = datetime.fromisoformat(author_date_str.replace("Z", "+00:00")).astimezone(timezone.utc)
                    dt_local = dt_utc.astimezone(now_local.tzinfo)
                    t_local = dt_local.strftime("%H:%M")
            except Exception:
                pass
            lines.append(f"- {t_local} {sha} {author_name}: {msg}")
        return "\n".join(lines)
    except requests.exceptions.RequestException as e:
        return f"An error occurred while fetching commits: {e}"
    except Exception as e:
        return f"An error occurred while fetching commits: {e}"

def _jira_auth_headers():
    jira_server = os.getenv("JIRA_SERVER")
    jira_username = os.getenv("JIRA_USERNAME")
    jira_api_token = os.getenv("JIRA_API")
    if not all([jira_server, jira_username, jira_api_token]):
        return None, None
    from requests.auth import HTTPBasicAuth
    return (jira_server, HTTPBasicAuth(jira_username, jira_api_token))

def _jira_count(jql: str) -> Optional[int]:
    base_and_auth = _jira_auth_headers()
    if not base_and_auth:
        return None
    jira_server, auth = base_and_auth
    headers = {"Accept": "application/json"}
    try:
        resp = requests.get(
            f"{jira_server}/rest/api/2/search",
            headers=headers,
            auth=auth,
            params={"jql": jql, "maxResults": 0, "fields": "none"},
        )
        if not resp.ok:
            return None
        data = resp.json()
        return int(data.get("total", 0))
    except Exception:
        return None

def _jira_summary_since(start_dt_local: datetime) -> dict:
    # Use Jira JQL date in UTC ISO 8601; Jira 2 API supports - use start local converted to UTC
    start_utc = start_dt_local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
    # Wrap in quotes as Jira expects
    start_str = start_utc
    completed = _jira_count(f"statusCategory = Done AND updated >= '{start_str}' AND assignee = currentUser()")
    raised = _jira_count(f"reporter = currentUser() AND created >= '{start_str}'")
    working = _jira_count("assignee = currentUser() AND statusCategory != Done")
    return {
        "completed": completed if completed is not None else "n/a",
        "raised": raised if raised is not None else "n/a",
        "working": working if working is not None else "n/a",
    }

def handle_cli_commands(effective_prompt: str) -> dict | None:
    """
    Handles CLI-like commands starting with '--'.
    Returns a dictionary with a 'response' or 'ui' key if a command is handled,
    otherwise returns None.
    """
    # --start day
    if effective_prompt and _has_flag(effective_prompt, ["--start day", "--start-day"]):
        repo, branch = _parse_repo_branch(effective_prompt)
        # Default repo from env if not provided
        if not repo:
            repo = os.getenv("GITHUB_DEFAULT_REPO")
        now_local = datetime.now().astimezone()
        _save_workday_start(now_local.isoformat(), repo, branch)
        msg = [
            f"Workday started at {now_local.strftime('%Y-%m-%d %H:%M %Z')}.",
        ]
        if repo:
            if branch:
                msg.append(f"Tracking GitHub {repo}@{branch}.")
            else:
                msg.append(f"Tracking GitHub {repo} (default branch).")
        else:
            msg.append("No repo provided; you can specify with repo=owner/name or --repo owner/name.")
        msg.append("Use --end day to get Jira and commit summary since start.")
        return {"response": "\n".join(msg)}

    # --end day
    if effective_prompt and _has_flag(effective_prompt, ["--end day", "--end-day"]):
        text_src = effective_prompt
        repo, branch = _parse_repo_branch(text_src)
        state = _load_workday_start()
        start_local: Optional[datetime] = None
        # Resolve start time
        if state and isinstance(state.get("start"), str):
            try:
                start_local = datetime.fromisoformat(state["start"]).astimezone()
            except Exception:
                start_local = None
        if not start_local:
            # Fallback to start of today
            now_local = datetime.now().astimezone()
            start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        # Resolve repo/branch
        if not repo and state:
            repo = state.get("repo")
            branch = branch or state.get("branch")
        if not repo:
            repo = os.getenv("GITHUB_DEFAULT_REPO")

        # Build GitHub summary
        gh_summary = None
        if repo:
            gh_summary = _github_commits_since(repo, start_local, branch)
        else:
            gh_summary = (
                "No repo configured. Provide repo=owner/name or set GITHUB_DEFAULT_REPO to include commits."
            )

        # Jira summary
        jira = _jira_summary_since(start_local)

        # Compose response
        parts = []
        parts.append(f"Workday summary since {start_local.strftime('%Y-%m-%d %H:%M %Z')}:")
        parts.append("")
        parts.append("Jira:")
        parts.append(f"- Completed issues: {jira['completed']}")
        parts.append(f"- Raised issues: {jira['raised']}")
        parts.append(f"- Working on: {jira['working']}")
        parts.append("")
        parts.append("GitHub commits:")
        if repo:
            parts.append(f"Repository: {repo}")
        parts.append(gh_summary)
        return {"response": "\n".join(parts)}
    
    return None
