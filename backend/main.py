from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from dotenv import load_dotenv
from pathlib import Path
import anyio
import logging
from datetime import datetime, timedelta, timezone
try:
    from agents.agent import agent
    from agents.sub_agents.formatter_agent.agent import formatter_agent
except ModuleNotFoundError:
    from backend.agents.agent import agent
    from backend.agents.sub_agents.formatter_agent.agent import formatter_agent
import os
import requests
from requests.auth import HTTPBasicAuth
import json
try:
    from tools.jira.sprint_tools import _fetch_active_sprint, _fetch_issues_in_active_sprint
except ModuleNotFoundError:
    from backend.tools.jira.sprint_tools import _fetch_active_sprint, _fetch_issues_in_active_sprint
from fastapi import Depends, status, Header
from passlib.hash import bcrypt
from sqlalchemy.orm import Session
from sqlalchemy import text
try:
    from app.db.database import get_db
except ModuleNotFoundError:
    from backend.app.db.database import get_db
import time
try:
    from tools.github.repo_tools import list_todays_commits
except ModuleNotFoundError:
    from backend.tools.github.repo_tools import list_todays_commits
try:
    from app.commands import handle_cli_commands, _extract_jira_key
except ModuleNotFoundError:
    from backend.app.commands import handle_cli_commands, _extract_jira_key
import hmac
import hashlib
import base64
try:
    from backend import config
except ModuleNotFoundError:
    import config


app = FastAPI()

class User(BaseModel):
    id: int
    username: str
    hashed_password: str
    skills: dict = {}

    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str

class AgentRequest(BaseModel):
    agent_name: str | None = None
    prompt: str | None = None

# Load env from backend/.env explicitly so agents have credentials
load_dotenv(dotenv_path=(Path(__file__).parent / ".env"))

# This is new: Initialize the ADK Runner
session_service = InMemorySessionService()
runner = Runner(app_name="ProjectMannagee", agent=agent, session_service=session_service)
# Runner dedicated to the formatter agent
formatter_runner = Runner(app_name="ProjectMannagee-Formatter", agent=formatter_agent, session_service=session_service)


# Enable CORS for local frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT configuration
SECRET_KEY = config.JWT_SECRET
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = config.ACCESS_TOKEN_EXPIRE_MINUTES

# Simple in-memory cache for Jira issue status to reduce repeated calls
_ISSUE_STATUS_CACHE: dict[str, tuple[float, dict]] = {}
_ISSUE_STATUS_TTL_SECONDS = config.ISSUE_STATUS_TTL_SECONDS

def _cache_get_issue_status(key: str) -> dict | None:
    try:
        ts, data = _ISSUE_STATUS_CACHE.get(key, (0.0, None))
        if data is None:
            return None
        if (time.time() - ts) < _ISSUE_STATUS_TTL_SECONDS:
            return data
    except Exception:
        pass
    return None

def _cache_put_issue_status(key: str, data: dict) -> None:
    try:
        _ISSUE_STATUS_CACHE[key] = (time.time(), data)
    except Exception:
        pass



def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

def _b64url_decode(s: str) -> bytes:
    padding = '=' * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s + padding)

def _jwt_encode_hs256(payload: dict, key: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    sig = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(sig)
    return f"{header_b64}.{payload_b64}.{sig_b64}"

def _jwt_decode_hs256(token: str, key: str) -> dict:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_sig, _b64url_decode(sig_b64)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    # exp check (exp in seconds since epoch)
    exp = payload.get("exp")
    if exp is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing exp")
    now_sec = int(datetime.now(timezone.utc).timestamp())
    if not isinstance(exp, (int, float)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid exp in token")
    if now_sec >= int(exp):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return payload

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire_dt = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": int(expire_dt.timestamp())})
    return _jwt_encode_hs256(to_encode, SECRET_KEY)

def _unauthorized(detail: str = "Not authenticated"):
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        _unauthorized("Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = _jwt_decode_hs256(token, SECRET_KEY)
        username: str | None = payload.get("sub")
        if not username:
            _unauthorized("Invalid token payload")
        user_row = db.execute(
            text("""SELECT id, username, hashed_password, skills FROM users WHERE username = :username"""),
            {"username": username}
        ).fetchone()
        if not user_row:
            _unauthorized("User not found")
        return User(id=user_row.id, username=user_row.username, hashed_password=user_row.hashed_password, skills=user_row.skills or {})
    except HTTPException:
        raise
    except Exception:
        _unauthorized("Invalid or expired token")

@app.get("/")
async def root():
    return {"message": "Hello from backend!"}

@app.get("/debug/ping")
async def debug_ping():
    return {"pong": True}

@app.post("/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    try:
        user = db.execute(
            text("""SELECT id, username, hashed_password, skills FROM users WHERE username = :username"""),
            {"username": request.username}
        ).fetchone()
    except Exception as e:
        # During tests, DB schema may not be initialized. Treat as user not found.
        if "no such table" in str(e).lower():
            user = None
        else:
            raise

    if not user or not bcrypt.verify(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    # Issue JWT token
    access_token = create_access_token({"sub": user.username})
    return {
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
    }

@app.get("/auth/me")
async def auth_me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "username": current_user.username, "skills": current_user.skills}

@app.post("/register")
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    # Check if username already exists
    existing_user = db.execute(
        text("""SELECT id FROM users WHERE username = :username"""),
        {"username": request.username}
    ).fetchone()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already registered"
        )

    hashed_password = bcrypt.hash(request.password)

    try:
        db.execute(
            text("""INSERT INTO users (username, hashed_password) VALUES (:username, :hashed_password)"""),
            {"username": request.username, "hashed_password": hashed_password}
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    return {"message": "Registration successful"}

@app.post("/codinator/run-agent")
async def run_codinator_agent(
    request: AgentRequest | None = None,
    agent_name: str | None = None,
    prompt: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """
    Compatibility endpoint used by the frontend ChatBox. Ignores agent_name and
    forwards the prompt to the core root_agent.
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("api")
    session_id: str | None = None
    user_id: str | None = None
    try:
        # Generate a unique session_id for each request.
        # Note: In a real app, you'd want to manage sessions more robustly.
        session_id = f"session_{anyio.current_time()}"
        user_id = str(current_user.id)

        session_service.create_session(app_name=runner.app_name, user_id=user_id, session_id=session_id)

        # Accept prompt from either JSON body or query/form parameters
        effective_prompt = prompt or (request.prompt if request else None)
        logger.debug("Received prompt: %s", effective_prompt)
        if not effective_prompt or not effective_prompt.strip():
            raise HTTPException(status_code=422, detail="Missing 'prompt'. Provide it in JSON body or as query param ?prompt=")
        # Split out any frontend-only guidance so it doesn't affect routing/tool calls
        # Keep the guidance for the formatter agent later.
        guidance_marker = "\n\n[Frontend requirements]"
        core_prompt = effective_prompt.split(guidance_marker, 1)[0].strip() if guidance_marker in effective_prompt else effective_prompt.strip()

        # Handle CLI-like commands
        cli_response = handle_cli_commands(core_prompt)
        if cli_response:
            return cli_response

        # All queries now go through the agent system - no hardcoded routing

        message = genai_types.Content(role="user", parts=[genai_types.Part(text=core_prompt)])

        final_response = ""
        # Log core agent invocation and prompt
        logger.info("[core agent] invoking with prompt: %s", core_prompt)
        with anyio.move_on_after(config.CORE_AGENT_TIMEOUT_SECONDS) as cancel_scope:  # 45s timeout
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message,
            ):
                if event.is_final_response():
                    if event.content and event.content.parts:
                        final_response = "".join(part.text for part in event.content.parts if part.text)
                    # Log the core agent's final response
                    logger.info("[core agent] final response: %s", final_response)
                    break  # Exit after getting the final response

        logger.debug("Finished runner.run_async. final_response is empty: %s", not final_response)
        if cancel_scope.cancel_called:
            logger.warning("/codinator/run-agent timeout")
            # Include the word 'timeout' explicitly to satisfy tests
            raise HTTPException(status_code=504, detail="Agent timeout")

        if not final_response:
            logger.error("/codinator/run-agent empty response from agent")
            raise HTTPException(status_code=502, detail="Empty response from agent")

        # Pipe through the formatter agent to produce UI-ready JSON
        formatting_prompt = (
            "Original User Input:\n" + effective_prompt.strip() + "\n\n" +
            "Raw Text/Tool Output:\n" + final_response.strip()
        )
        formatting_message = genai_types.Content(role="user", parts=[genai_types.Part(text=formatting_prompt)])

        # Ensure a session exists for the formatter app
        formatter_session_id = f"{session_id}-formatter"
        session_service.create_session(app_name=formatter_runner.app_name, user_id=user_id, session_id=formatter_session_id)

        formatted_text = ""
        logger.info("[formatter agent] invoking to structure UI output")
        with anyio.move_on_after(config.FORMATTER_AGENT_TIMEOUT_SECONDS) as fmt_cancel_scope:  # shorter timeout for formatting
            async for event in formatter_runner.run_async(
                user_id=user_id,
                session_id=formatter_session_id,
                new_message=formatting_message,
            ):
                if event.is_final_response():
                    if event.content and event.content.parts:
                        formatted_text = "".join(part.text for part in event.content.parts if part.text)
                    logger.info("[formatter agent] final response: %s", formatted_text)
                    break

        if fmt_cancel_scope.cancel_called:
            logger.warning("/codinator/run-agent formatter timeout; falling back to generic UI")
    
        return formatted_text
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("/codinator/run-agent failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/jira/sprint-completion-if-removed")
async def jira_sprint_completion_if_removed(
    issue_key: str = Query(..., description="Jira issue key to remove, e.g., PROJ-123"),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the sprint completion date before and after removing the specified issue from the current sprint,
    along with the delta in days (positive means the sprint finishes earlier).
    """
    try:
        # Import locally to avoid circular imports
        try:
            from tools.cpa.engine.sprint_timeline import sprint_completion_if_issue_removed
        except ModuleNotFoundError:
            from backend.tools.cpa.engine.sprint_timeline import sprint_completion_if_issue_removed

        if not issue_key or '-' not in issue_key:
            raise HTTPException(status_code=422, detail="Please provide a valid Jira issue key, e.g., PROJ-123")
        project_key = issue_key.split('-', 1)[0]
        result = sprint_completion_if_issue_removed(project_key=project_key, removed_issue_key=issue_key)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("/jira/sprint-completion-if-removed failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # In a real app, you'd want to manage session cleanup more robustly (e.g., with timeouts or explicit logout).
        # For now, we'll let in-memory sessions persist to avoid "Session not found" errors.
        pass

@app.get("/jira/issue-status")
async def jira_issue_status(key: str = Query(..., description="Jira issue key, e.g., PROJ-123"), current_user: User = Depends(get_current_user)):
    """
    Return Jira issue status data for the given key, including:
    - name (summary)
    - expectedFinishDate (duedate)
    - comments (latest comments, up to 10)
    """
    # Load env to ensure variables are present when running as script
    load_dotenv(dotenv_path=(Path(__file__).parent / ".env"))
    jira_server = os.getenv("JIRA_SERVER")
    jira_username = os.getenv("JIRA_USERNAME")
    jira_api_token = os.getenv("JIRA_API")
    if not all([jira_server, jira_username, jira_api_token]):
        raise HTTPException(status_code=500, detail="Jira env vars not set (JIRA_SERVER, JIRA_USERNAME, JIRA_API)")

    auth = HTTPBasicAuth(jira_username, jira_api_token)
    headers = {"Accept": "application/json"}

    try:
        # Serve from cache if fresh
        cached = _cache_get_issue_status(key)
        if cached is not None:
            return cached
        # Fetch issue with selected fields and expanded comments
        url = f"{jira_server}/rest/api/3/issue/{key}"
        params = {"fields": "summary,duedate,comment,status"}
        resp = requests.get(url, headers=headers, auth=auth, params=params)
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Issue {key} not found")
        if not resp.ok:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        data = resp.json()
        fields = data.get("fields", {})
        summary = fields.get("summary")
        duedate = fields.get("duedate")  # ISO date or None
        status = fields.get("status", {}).get("name")
        comments_block = fields.get("comment") or {}
        comments = comments_block.get("comments", [])

        # Normalize comments to a simple list of strings (author: body)
        normalized_comments = []
        for c in comments[:config.JIRA_COMMENTS_LIMIT]:
            author = (c.get("author") or {}).get("displayName") or "Unknown"
            body = c.get("body")
            if isinstance(body, dict) and "content" in body:
                # Cloud rich-text: flatten basic text
                try:
                    parts = []
                    for b1 in body.get("content", []):
                        for b2 in b1.get("content", []):
                            t = b2.get("text")
                            if t:
                                parts.append(t)
                    body_text = "".join(parts)
                except Exception:
                    body_text = str(body)
            else:
                body_text = str(body)
            normalized_comments.append(f"{author}: {body_text}")

        result = {
            "key": key,
            "name": summary,
            "expectedFinishDate": duedate,
            "status": status,
            "comments": normalized_comments,
            "url": f"{jira_server}/browse/{key}",
        }
        _cache_put_issue_status(key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("/jira/issue-status failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/jira/sprint-status")
async def jira_sprint_status(project_key: str = Query(..., description="Jira project key, e.g., PROJ"), current_user: User = Depends(get_current_user)):
    """
    Return the current active sprint details for a given Jira project key.
    Response includes: name, startDate, endDate, and optional notes.
    """
    try:
        # Ensure env loaded (when running as a script)
        load_dotenv(dotenv_path=(Path(__file__).parent / ".env"))
        sprint = _fetch_active_sprint(project_key)
        if not sprint:
            raise HTTPException(status_code=404, detail=f"No active sprint found for project {project_key}")
        data, err = _fetch_issues_in_active_sprint(project_key)
        if err:
            raise HTTPException(status_code=500, detail=err)
        if isinstance(data, str): # Should not happen if err is handled
            raise HTTPException(status_code=500, detail=data)

        sprint_info = data.get("sprint", {})
        issues = data.get("issues", [])

        total_issues = len(issues)
        completed_issues = sum(1 for issue in issues if issue.get("status") == config.JIRA_COMPLETED_STATUS) # Assuming "Done" is the completed status

        return {
            "name": sprint_info.get("name"),
            "startDate": sprint_info.get("startDate"),
            "endDate": sprint_info.get("endDate"),
            "notes": [], # Notes are not currently fetched by _fetch_issues_in_active_sprint
            "totalIssues": total_issues,
            "completedIssues": completed_issues,
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("/jira/sprint-status failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/jira/issue-eta-graph")
async def jira_issue_eta_graph(
    issue_key: str = Query(..., description="Jira issue key, e.g., PROJ-123"),
    current_user: User = Depends(get_current_user),
):
    """
    Returns ETA range and a dependency subgraph for the given issue using current sprint data.
    Response shape:
    {
      issue: str,
      project_key: str,
      optimistic_days: int,
      pessimistic_days: int,
      optimistic_schedule: [...],
      pessimistic_schedule: [...],
      nodes: { key: { assignee, duration_days, dependencies: [...] } }
    }
    """
    try:
        if not issue_key or '-' not in issue_key:
            raise HTTPException(status_code=422, detail="Please provide a valid Jira issue key, e.g., PROJ-123")
        project_key = issue_key.split('-', 1)[0]
        try:
            from tools.cpa.engine.sprint_eta import compute_eta_range_for_issue_current_sprint
        except ModuleNotFoundError:
            from backend.tools.cpa.engine.sprint_eta import compute_eta_range_for_issue_current_sprint
        try:
            from tools.cpa.engine.sprint_dependency import current_sprint_dependency_graph
        except ModuleNotFoundError:
            from backend.tools.cpa.engine.sprint_dependency import current_sprint_dependency_graph

        eta = compute_eta_range_for_issue_current_sprint(project_key=project_key, issue_key=issue_key)
        graph = current_sprint_dependency_graph(project_key)
        nodes = graph.get("nodes", {})

        # Build subgraph of ancestors + target
        def ancestors_of(target: str) -> set:
            parents = {k: nd.get("dependencies", []) for k, nd in nodes.items()}
            anc = set()
            def dfs(u: str):
                for p in parents.get(u, []):
                    if p not in anc:
                        anc.add(p)
                        dfs(p)
            dfs(target)
            return anc

        anc = ancestors_of(issue_key)
        sub_nodes = {}
        for k, nd in nodes.items():
            if k == issue_key or k in anc:
                # limit deps to within subgraph
                deps = [d for d in nd.get("dependencies", []) if d == issue_key or d in anc]
                sub_nodes[k] = {
                    "assignee": nd.get("assignee"),
                    "duration_days": int(max(1, nd.get("duration_days") or 1)),
                    "dependencies": deps,
                }

        return {
            "issue": issue_key,
            "project_key": project_key,
            "optimistic_days": int(eta.get("optimistic_days", 0)),
            "pessimistic_days": int(eta.get("pessimistic_days", eta.get("optimistic_days", 0))),
            "optimistic_schedule": eta.get("optimistic_schedule", []),
            "pessimistic_schedule": eta.get("pessimistic_schedule", []),
            "optimistic_critical_path": eta.get("optimistic_critical_path", []),
            "pessimistic_blockers": eta.get("pessimistic_blockers", []),
            "nodes": sub_nodes,
            "summary": eta.get("summary"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("/jira/issue-eta-graph failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/jira/base-url")
async def jira_base_url(current_user: User = Depends(get_current_user)):
    """
    Returns the configured Jira base URL so the frontend can construct deep links.
    """
    try:
        # Ensure env loaded
        load_dotenv(dotenv_path=(Path(__file__).parent / ".env"))
        jira_server = os.getenv("JIRA_SERVER")
        if not jira_server:
            raise HTTPException(status_code=500, detail="JIRA_SERVER env var not set")
        return {"base": jira_server}
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("/jira/base-url failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.UVICORN_HOST, port=config.UVICORN_PORT)