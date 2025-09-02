from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .agents.agent import root_agent
from .agents.sub_agents.jira_sprint_agent.agent import (
    summarize_current_sprint_v1,
    summarize_current_sprint_default,
)
from dotenv import load_dotenv
from pathlib import Path
import anyio
import logging
import re

app = FastAPI()

# Load env from backend/.env explicitly so agents have credentials
load_dotenv(dotenv_path=(Path(__file__).parent / ".env"))

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

def _to_text(resp) -> str:
    """Normalize ADK Agent outputs to a user-facing string."""
    try:
        if resp is None:
            return ""
        if isinstance(resp, str):
            return resp.strip()
        if isinstance(resp, dict):
            # Common fields in various ADK responses
            for k in ("text", "response", "output", "content", "message"):
                v = resp.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        # Fallback to stringification
        s = str(resp)
        return s.strip()
    except Exception:
        return ""

@app.get("/")
async def root():
    return {"message": "Hello from backend!"}

@app.get("/debug/ping")
async def debug_ping():
    return {"pong": True}

@app.post("/codinator/run-agent")
async def run_codinator_agent(agent_name: str, prompt: str):
    """
    Compatibility endpoint used by the frontend ChatBox. Ignores agent_name and
    forwards the prompt to the core root_agent.
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("api")
    logger.info("/codinator/run-agent start | agent_name=%s", agent_name)
    try:
        # Prefer the ADK Agent.run if available
        run_fn = getattr(root_agent, "run", None)
        if callable(run_fn):
            with anyio.move_on_after(45) as cancel_scope:  # 45s timeout
                response = await anyio.to_thread.run_sync(run_fn, prompt)
            if cancel_scope.cancel_called:
                logger.warning("/codinator/run-agent timeout")
                raise HTTPException(status_code=504, detail="Agent timed out")
            text = _to_text(response)
            if not text:
                logger.error("/codinator/run-agent empty response from agent | raw=%r", response)
                raise HTTPException(status_code=502, detail="Empty response from agent")
            logger.info("/codinator/run-agent success (root_agent.run)")
            return {"response": text}

        # Fallback: lightweight router for common Jira intents
        logger.info("/codinator/run-agent using fallback router (no .run on Agent)")
        p = (prompt or "").strip()
        # e.g., "what is the current sprint for TESTPROJ" or "current sprint for TESTPROJ"
        m = re.search(r"current\s+sprint\s+for\s+([A-Za-z0-9_\-]+)", p, flags=re.IGNORECASE)
        if m:
            project_key = m.group(1)
            with anyio.move_on_after(45) as cancel_scope:
                response = await anyio.to_thread.run_sync(summarize_current_sprint_v1, project_key)
            if cancel_scope.cancel_called:
                logger.warning("/codinator/run-agent timeout (fallback)")
                raise HTTPException(status_code=504, detail="Agent timed out")
            text = _to_text(response)
            if not text:
                raise HTTPException(status_code=502, detail="Empty response from fallback agent")
            return {"response": text}

        # If user didn’t specify project key, try memory-based default
        if re.search(r"current\s+sprint", p, flags=re.IGNORECASE):
            with anyio.move_on_after(45) as cancel_scope:
                response = await anyio.to_thread.run_sync(summarize_current_sprint_default)
            if cancel_scope.cancel_called:
                logger.warning("/codinator/run-agent timeout (fallback default)")
                raise HTTPException(status_code=504, detail="Agent timed out")
            text = _to_text(response)
            if not text:
                text = "Please provide a Jira project_key, e.g., 'current sprint for TESTPROJ'."
            return {"response": text}

        # Generic fallback
        raise HTTPException(
            status_code=400,
            detail="Unsupported prompt in fallback mode and root agent .run is unavailable.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("/codinator/run-agent failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)