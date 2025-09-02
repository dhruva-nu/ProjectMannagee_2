from fastapi import FastAPI, HTTPException
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)