from fastapi import FastAPI
from .agents.jira_agent import get_latest_sprint
from .agents.codinator_agent import codinator_agent, run_agent # Import codinator_agent and run_agent

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello from backend!"}

@app.get("/jira/latest-sprint")
async def get_jira_latest_sprint():
    return {"latest_sprint": get_latest_sprint()}

@app.post("/codinator/run-agent") # New endpoint for codinator agent
async def run_codinator_agent(agent_name: str, prompt: str):
    response = run_agent(agent_name, prompt)
    return {"response": response}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)