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
from agents.agent import agent
import os
import requests
from requests.auth import HTTPBasicAuth
from tools.jira.sprint_tools import _fetch_active_sprint
from fastapi import Depends, status, Header
from passlib.hash import bcrypt
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.database import get_db
from jose import jwt, JWTError
import re
import time

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


# Enable CORS for local frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "*",  # widen during development; consider restricting in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT configuration
SECRET_KEY = os.getenv("JWT_SECRET", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Simple in-memory cache for Jira issue status to reduce repeated calls
_ISSUE_STATUS_CACHE: dict[str, tuple[float, dict]] = {}
_ISSUE_STATUS_TTL_SECONDS = int(os.getenv("ISSUE_STATUS_TTL_SECONDS", "30"))

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

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def _unauthorized(detail: str = "Not authenticated"):
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        _unauthorized("Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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
    except JWTError:
        _unauthorized("Invalid or expired token")

@app.get("/")
async def root():
    return {"message": "Hello from backend!"}

@app.get("/debug/ping")
async def debug_ping():
    return {"pong": True}

@app.post("/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.execute(
        text("""SELECT id, username, hashed_password, skills FROM users WHERE username = :username"""),
        {"username": request.username}
    ).fetchone()

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
        if not effective_prompt or not effective_prompt.strip():
            raise HTTPException(status_code=422, detail="Missing 'prompt'. Provide it in JSON body or as query param ?prompt=")

        # Lightweight pre-router: handle simple Jira status queries locally to avoid LLM/tool calls
        # Patterns like: "what is the status of issue ABC-123" or "jira status for ABC-123"
        if effective_prompt:
            prompt_lc = effective_prompt.lower()
            # Extract a plausible JIRA key (prefix-num)
            m = re.search(r"\b([A-Z][A-Z0-9]+-\d+)\b", effective_prompt, flags=re.IGNORECASE)
            if m and ("status" in prompt_lc) and ("issue" in prompt_lc or "jira" in prompt_lc):
                issue_key = m.group(1)
                # Return a structured UI directive for the frontend to consume directly
                logging.getLogger("api").info("/codinator/run-agent pre-router handled jira status for %s", issue_key)
                return {"ui": "jira_status", "key": issue_key}

        message = genai_types.Content(role="user", parts=[genai_types.Part(text=effective_prompt)])

        final_response = ""
        with anyio.move_on_after(45) as cancel_scope:  # 45s timeout
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message,
            ):
                if event.is_final_response():
                    if event.content and event.content.parts:
                        final_response = "".join(part.text for part in event.content.parts if part.text)
                    break  # Exit after getting the final response

        if cancel_scope.cancel_called:
            logger.warning("/codinator/run-agent timeout")
            raise HTTPException(status_code=504, detail="Agent timed out")

        if not final_response:
            logger.error("/codinator/run-agent empty response from agent")
            raise HTTPException(status_code=502, detail="Empty response from agent")

        logger.info("/codinator/run-agent success")
        return {"response": final_response}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("/codinator/run-agent failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Delete the in-memory session so prior chat turns are not retained
        try:
            if session_id and user_id:
                session_service.delete_session(app_name=runner.app_name, user_id=user_id, session_id=session_id)
        except Exception:
            # Best-effort cleanup; do not block response on cleanup failures
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
        params = {"fields": "summary,duedate,comment"}
        resp = requests.get(url, headers=headers, auth=auth, params=params)
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Issue {key} not found")
        if not resp.ok:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        data = resp.json()
        fields = data.get("fields", {})
        summary = fields.get("summary")
        duedate = fields.get("duedate")  # ISO date or None
        comments_block = fields.get("comment") or {}
        comments = comments_block.get("comments", [])

        # Normalize comments to a simple list of strings (author: body)
        normalized_comments = []
        for c in comments[:10]:
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
            "comments": normalized_comments,
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
        return {
            "name": sprint.get("name"),
            "startDate": sprint.get("startDate"),
            "endDate": sprint.get("endDate"),
            "notes": [],
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("/jira/sprint-status failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)