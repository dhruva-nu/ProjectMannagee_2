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
import re
from .agents.agent import agent
import os
import requests
from requests.auth import HTTPBasicAuth
from backend.tools.jira.sprint_tools import _fetch_active_sprint

app = FastAPI()

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

@app.get("/")
async def root():
    return {"message": "Hello from backend!"}

@app.get("/debug/ping")
async def debug_ping():
    return {"pong": True}

@app.post("/codinator/run-agent")
async def run_codinator_agent(
    request: AgentRequest | None = None,
    agent_name: str | None = None,
    prompt: str | None = None,
):
    """
    Compatibility endpoint used by the frontend ChatBox. Ignores agent_name and
    forwards the prompt to the core root_agent.
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("api")
    try:
        # Generate a unique session_id for each request.
        # Note: In a real app, you'd want to manage sessions more robustly.
        session_id = f"session_{anyio.current_time()}"
        user_id = "user_123"  # A placeholder user_id

        session_service.create_session(app_name=runner.app_name, user_id=user_id, session_id=session_id)

        # Accept prompt from either JSON body or query/form parameters
        effective_prompt = prompt or (request.prompt if request else None)
        if not effective_prompt or not effective_prompt.strip():
            raise HTTPException(status_code=422, detail="Missing 'prompt'. Provide it in JSON body or as query param ?prompt=")

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

@app.get("/jira/issue-status")
async def jira_issue_status(key: str = Query(..., description="Jira issue key, e.g., PROJ-123")):
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

        return {
            "key": key,
            "name": summary,
            "expectedFinishDate": duedate,
            "comments": normalized_comments,
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("/jira/issue-status failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/jira/sprint-status")
async def jira_sprint_status(project_key: str = Query(..., description="Jira project key, e.g., PROJ")):
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