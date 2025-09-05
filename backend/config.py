
import os

# CORS settings
CORS_ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

# JWT configuration
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "3600"))

# Jira issue status cache
ISSUE_STATUS_TTL_SECONDS = int(os.getenv("ISSUE_STATUS_TTL_SECONDS", "30"))

# Agent timeouts
CORE_AGENT_TIMEOUT_SECONDS = int(os.getenv("CORE_AGENT_TIMEOUT_SECONDS", "45"))
FORMATTER_AGENT_TIMEOUT_SECONDS = int(os.getenv("FORMATTER_AGENT_TIMEOUT_SECONDS", "20"))

# Jira comments limit
JIRA_COMMENTS_LIMIT = int(os.getenv("JIRA_COMMENTS_LIMIT", "10"))

# Jira completed status
JIRA_COMPLETED_STATUS = os.getenv("JIRA_COMPLETED_STATUS", "Done")

# Uvicorn server settings
UVICORN_HOST = os.getenv("UVICORN_HOST", "0.0.0.0")
UVICORN_PORT = int(os.getenv("UVICORN_PORT", "8000"))
