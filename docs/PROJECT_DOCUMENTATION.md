### 1. Core Application (`backend/main.py`)

This file serves as the entry point for the FastAPI backend application. It sets up the web server, defines API endpoints, handles user authentication, and orchestrates interactions with the Google ADK agents and various Jira/GitHub tools.

**Key Features:**

*   **FastAPI Initialization:** Creates the FastAPI application instance.
*   **CORS Middleware:** Configures Cross-Origin Resource Sharing to allow requests from the frontend development server.
*   **User Authentication (JWT):**
    *   Defines Pydantic models for `User`, `LoginRequest`, and `RegisterRequest`.
    *   Implements JWT (JSON Web Token) encoding and decoding for secure user sessions.
    *   Provides endpoints for user registration (`/register`), login (`/login`), and fetching current user details (`/auth/me`).
    *   Uses `passlib` (bcrypt) for password hashing.
    *   Integrates with the database (`app.db.database`) for user storage.
*   **ADK (Agent Development Kit) Integration:**
    *   Initializes `Runner` instances for the main `agent` (named "ProjectMannagee") and a dedicated `formatter_agent` (named "ProjectMannagee-Formatter").
    *   Uses `InMemorySessionService` for managing agent sessions.
*   **Jira Issue Status Cache:** Implements a simple in-memory cache (`_ISSUE_STATUS_CACHE`) to reduce redundant API calls to Jira for issue status, with a configurable TTL (Time-To-Live).
*   **Main Agent Interaction Endpoint (`/codinator/run-agent`):**
    *   This is the primary API endpoint for the frontend to communicate with the AI agents.
    *   It accepts a `prompt` from the user.
    *   **Lightweight Pre-routing:** Before invoking the main AI agent, it attempts to handle common Jira-related queries (e.g., "status of issue ABC-123", "ETA for ABC-123", "sprint completion if issue removed") directly. If a match is found, it returns a structured UI directive to the frontend, bypassing the LLM for faster responses.
    *   **CLI Command Handling:** Delegates to `app.commands.handle_cli_commands` for processing specific CLI-like commands (e.g., `--start day`, `--end day`).
    *   **Core Agent Invocation:** If not handled by pre-routing or CLI commands, the `prompt` is forwarded to the main `agent` (LLM).
    *   **Formatter Agent Pipeline:** The raw response from the main `agent` is then piped through the `formatter_agent`. This specialized agent's role is to convert the raw text/tool output into a structured JSON format that the frontend can easily consume to render dynamic UI components.
*   **Direct Jira API Endpoints:**
    *   `/jira/sprint-completion-if-removed`: Calculates the impact of removing an issue on sprint completion.
    *   `/jira/issue-status`: Fetches detailed status for a given Jira issue.
    *   `/jira/sprint-status`: Retrieves details about the current active sprint for a project.
    *   `/jira/issue-eta-graph`: Computes and returns ETA (Estimated Time of Arrival) and dependency graph information for a Jira issue, leveraging Critical Path Analysis (CPA).
    *   `/jira/base-url`: Provides the configured Jira base URL to the frontend for constructing deep links.
*   **Environment Variables:** Loads environment variables from a `.env` file (specifically `backend/.env`) to configure API keys and other sensitive information.

### 2. Database (`backend/app/db/`)

This directory defines the database schema, connection, and data loading mechanisms for the backend.

#### `backend/app/db/schema.sql`

This SQL file defines the PostgreSQL database schema used by the application.

*   **`projects` table:** Stores information about projects.
    *   `id`: Serial primary key.
    *   `name`: Text, not null.
*   **`tasks` table:** Stores individual tasks, often mapped to Jira issues.
    *   `id`: VARCHAR(50), primary key (e.g., "PROJ-123").
    *   `project_id`: INT, foreign key referencing `projects.id`.
    *   `name`: TEXT, not null (summary/title of the task).
    *   `estimate_days`: FLOAT, not null (estimated duration in days).
    *   `start_date`: DATE.
    *   `end_date`: DATE.
    *   `assignee`: INT, foreign key referencing `users.id` (initially TEXT, then altered to INT).
*   **`dependencies` table:** Stores task dependencies.
    *   `id`: Serial primary key.
    *   `task_id`: VARCHAR(50), foreign key referencing `tasks.id` (the task that depends).
    *   `depends_on`: VARCHAR(50), foreign key referencing `tasks.id` (the task it depends on).
*   **`users` table:** Stores user authentication and profile information.
    *   `id`: Serial primary key.
    *   `username`: TEXT, unique, not null.
    *   `hashed_password`: TEXT, not null.
    *   `skills`: JSONB, defaults to an empty JSON object.

#### `backend/app/db/database.py`

This file handles the SQLAlchemy database connection and session management.

*   **`DATABASE_URL`:** Configured via environment variable (`DATABASE_URL`), defaults to a PostgreSQL connection string.
*   **`engine`:** Creates a SQLAlchemy engine for connecting to the database.
*   **`SessionLocal`:** Configures a sessionmaker for creating database sessions.
*   **`get_db()`:** A FastAPI dependency function that provides a database session to API endpoints. It ensures the session is closed after the request is processed.

#### `backend/app/db/models.py`

This file defines Pydantic models that represent the data structures for tasks, projects, and dependencies. These models are used for data validation, serialization, and deserialization, especially when interacting with the API and the CPA engine.

*   **`DependencyModel`:**
    *   `task_id`: string
    *   `depends_on`: string
*   **`TaskModel`:**
    *   `id`: string (e.g., Jira issue key)
    *   `name`: string
    *   `estimate_days`: float
    *   `start_date`: optional date
    *   `end_date`: optional date
    *   `assignee`: optional string (username)
    *   `dependencies`: list of strings (issue keys)
*   **`ProjectModel`:**
    *   `id`: integer
    *   `name`: string
    *   `tasks`: list of `TaskModel`

#### `backend/app/db/db_loader.py`

This module contains functions to load project and task data from the database into the Pydantic `ProjectModel` and `TaskModel` structures, which are then used by the CPA engine.

*   **`load_project_from_db(session, project_id)`:**
    *   Fetches tasks and their dependencies for a given `project_id` from the database.
    *   Handles different `assignee` column types (e.g., `assignee_id` as FK, `assignee` as INT for user ID, or `assignee` as TEXT for username) to correctly retrieve the assignee's username.
    *   Constructs `TaskModel` instances, including their dependencies.
    *   Returns a `ProjectModel` instance populated with the retrieved tasks.

### 3. Commands (`backend/app/commands.py`)

This module implements CLI-like commands that can be triggered via the `/codinator/run-agent` endpoint. It provides utility functions for parsing user input and interacting with GitHub and Jira.

**Key Functions:**

*   **`_extract_jira_key(text: str)`:**
    *   Parses free-form text to extract a plausible Jira issue key (e.g., "PROJ-123") without using regular expressions. It looks for patterns like `[LETTERS][NUMBERS]-[DIGITS]`.
*   **`_has_flag(text: str, variants: list[str])`:**
    *   Checks if the input text contains any of the specified CLI-like flags (e.g., `--start day`).
*   **`_parse_repo_branch(text: str)`:**
    *   Parses a repository name (owner/repo) and an optional branch from free-form text, supporting various syntaxes (e.g., `repo=owner/name`, `--repo owner/name`).
*   **Workday State Management:**
    *   `_state_file_path()`: Determines the path to a JSON file (`.workday_state.json`) used to store workday start information.
    *   `_save_workday_start()`: Saves the workday start time, and optionally the GitHub repository and branch being tracked, to the state file.
    *   `_load_workday_start()`: Loads the saved workday state from the file.
*   **GitHub Integration:**
    *   `_github_commits_since(repo_full_name, start_dt_local, branch)`: Fetches and formats a list of Git commits for a given repository and time range using the GitHub API. Requires `GITHUB_TOKEN` environment variable.
*   **Jira Integration:**
    *   `_jira_auth_headers()`: Retrieves Jira server URL, username, and API token from environment variables and prepares HTTPBasicAuth credentials.
    *   `_jira_count(jql)`: Executes a Jira JQL query and returns the total count of matching issues.
    *   `_jira_search(jql, max_results)`: Executes a Jira JQL query and returns a simplified list of issues (key, summary, status, due date).
    *   **`_jira_summary_since(start_dt_local)`:** Provides a summary of Jira activity (completed, raised, working issues) since a given local datetime.
*   **`handle_cli_commands(effective_prompt)`:**
    *   The main function for processing CLI-like commands.
    *   **`--start day`:** Records the workday start time, optionally tracks a GitHub repository, and provides a summary of Jira tasks due today or in progress.
    *   **`--end day`:** Provides a summary of GitHub commits and Jira activity (completed, raised, working issues) since the recorded workday start time.

### 4. Agents (`backend/agents/`)

This directory contains the definitions for the various AI agents that form the core intelligence of the "ProjectMannagee" application. These agents are built using the Google ADK (Agent Development Kit).

#### `backend/agents/agent.py`

This file defines the **core orchestrating agent** of the system. Its primary responsibility is to understand user requests and delegate tasks to specialized sub-agents or directly call tools based on their capabilities.

*   **`agent` (Core Agent):**
    *   **Name:** "core"
    *   **Model:** `gemini-2.0-flash` (indicating it uses Google's Gemini model).
    *   **Description:** "Coordinates between all sub-agents to complete user tasks."
    *   **Instruction:** A detailed prompt that guides the LLM on how to behave, when to use specific tools or sub-agents, and what parameters to collect. It emphasizes:
        *   Delegation to sub-agents based on expertise.
        *   Direct tool calls for specific actions (e.g., `who_is_assigned`, `transition_issue_status`).
        *   Parameter collection for tools (e.g., `organization` for GitHub, `issue_key` and `query` for Jira).
        *   Handling of Jira-specific intents (sprint summaries, hypothetical planning, blockers, ETA).
        *   Instructions for adding comments to Jira issues.
    *   **`sub_agents`:** Lists all the specialized sub-agents that the core agent can delegate to:
        *   `jira_agent`
        *   `github_repo_agent`
        *   `jira_cpa_agent`
        *   `cpa_engine_agent`
    *   **`tools`:** Defines the tools available to the core agent. These include:
        *   `FunctionTool(who_is_assigned)`: Directly looks up Jira issue assignees.
        *   `FunctionTool(answer_jira_query)`: Answers general questions about Jira issues.
        *   `FunctionTool(transition_issue_status)`: Changes the status of a Jira issue.
        *   `AgentTool(...)`: Wrappers for each sub-agent, allowing the core agent to call their exposed functionalities.

#### `backend/agents/sub_agents/cpa_engine_agent/agent.py`

This agent is responsible for performing Critical Path Analysis (CPA) related operations, often by interacting with the database and Jira.

*   **`cpa_engine_agent`:**
    *   **Name:** "cpa_engine_agent"
    *   **Model:** `gemini-2.0-flash`
    *   **Description:** "CPA Engine Agent: syncs Jira to DB and runs Critical Path Analysis over tasks/dependencies."
    *   **Instruction:** Guides the agent to return concise structured JSON from its tools.
    *   **`tools`:** Exposes a suite of deterministic functions for CPA:
        *   `refresh_from_jira`: Syncs Jira data to the local database.
        *   `run_cpa`: Executes the CPA calculation.
        *   `get_critical_path`: Retrieves the critical path of a project.
        *   `get_task_slack`: Gets the slack for a specific task.
        *   `get_project_duration`: Calculates the overall project duration.
        *   `summarize_current_sprint_cpa`: Provides a concise CPA summary for the current sprint.
        *   `current_sprint_cpa_timeline`: Generates a timeline for the current sprint based on CPA.
        *   `estimate_issue_completion_in_current_sprint`: Estimates the completion date for a single issue.
        *   `compute_eta_range_for_issue_current_sprint`: Computes optimistic/pessimistic ETA for an issue.
        *   `estimate_issue_eta_wrapper` and `estimate_issue_eta_days`: Convenience wrappers for ETA estimation.

#### `backend/agents/sub_agents/formatter_agent/agent.py`

This is a crucial agent dedicated solely to formatting the output of other agents into a consistent, UI-ready JSON structure. This centralizes presentation logic and keeps other agents focused on their core tasks.

*   **`formatter_agent`:**
    *   **Name:** "formatter_agent"
    *   **Model:** `gemini-2.5-flash` (a more capable model, likely for better JSON generation).
    *   **Description:** "Formatting agent that converts raw strings from other agents into structured UI-ready JSON."
    *   **Instruction:** Provides detailed rules for formatting, including:
        *   Receiving "Original User Input" and "Raw Text/Tool Output".
        *   Deciding the best UI directive (`ui` field) based on both inputs.
        *   Returning a single JSON object with a top-level `ui` key and a `data` object.
        *   Mentally parsing existing JSON and normalizing it to the UI schema.
        *   Wrapping plain text in a sensible UI type (e.g., `generic`).
        *   Specific directives for `user_card` (assignee info) and `issue_list` (sprint issues).
        *   Lists common UI types (e.g., `jira_status`, `eta_estimate`, `cpa_summary`).
        *   Emphasizes valid JSON output.
    *   **`tools`:** This agent has no direct tools; its functionality is driven by its instructions and the input it receives.

#### `backend/agents/sub_agents/github_repo_agent/agent.py`

This agent specializes in interacting with the GitHub API to retrieve repository and commit information.

*   **`github_repo_agent`:**
    *   **Name:** "github_repo_agent"
    *   **Model:** `gemini-2.0-flash`
    *   **Description:** "GitHub sub-agent that lists repositories and related metadata."
    *   **Instruction:** Guides the agent on how to use its tools, specifically for listing repositories (requires `organization`) and listing today's commits (requires `repo_full_name`, optional `branch`).
    *   **`tools`:**
        *   `FunctionTool(list_repositories)`: Lists repositories for a given organization.
        *   `FunctionTool(list_todays_commits)`: Lists commits made today for a specified repository.

#### `backend/agents/sub_agents/jira_agent/agent.py`

This agent focuses on providing summaries and overviews of Jira sprints and issues. It leverages internal memory to avoid repeatedly asking for `project_key`.

*   **`jira_agent`:**
    *   **Name:** "jira_agent"
    *   **Model:** `gemini-2.0-flash`
    *   **Description:** "Jira sub-agent handling sprint summaries and issue overviews."
    *   **Instruction:** Emphasizes using "no-arg tools" (e.g., `summarize_current_sprint_default`) if a `project_key` is remembered, and explicit tools (e.g., `summarize_current_sprint_v1`) if a `project_key` is provided by the user. It should only ask for `project_key` if neither is available.
    *   **`tools`:**
        *   `FunctionTool(summarize_current_sprint_v1)`: Summarizes the current sprint for a given project key.
        *   `FunctionTool(summarize_issues_in_sprint_v1)`: Summarizes issues in the current sprint for a given project key.
        *   `FunctionTool(summarize_current_sprint_default)`: Summarizes the current sprint using a remembered project key.
        *   `FunctionTool(summarize_issues_in_sprint_default)`: Summarizes issues in the current sprint using a remembered project key.
        *   `FunctionTool(get_issues_assigned_to_user)`: Retrieves issues assigned to a specific user.
        *   `FunctionTool(get_issues_for_active_sprint_v1)`: Gets a list of issues for the active sprint for a given project key.
        *   `FunctionTool(get_issues_for_active_sprint_default)`: Gets a list of issues for the active sprint using a remembered project key.
        *   `FunctionTool(add_comment_to_jira_issue)`: Adds a comment to a Jira issue.

#### `backend/agents/sub_agents/jira_cpa_agent/agent.py`

This agent is designed for more complex Jira analysis and sprint planning queries, often involving Critical Path Analysis (CPA).

*   **`jira_cpa_agent`:**
    *   **Name:** "jira_cpa_agent"
    *   **Model:** `gemini-2.0-flash`
    *   **Description:** "CPA sub-agent for answering Jira issue and sprint planning queries using context and project knowledge."
    *   **Instruction:** Provides specific guidance for:
        *   Identifying blockers (`what_is_blocking`).
        *   Assignee queries (`who_is_assigned`).
        *   Generic issue Q&A (`answer_jira_query`).
        *   Hypothetical sprint planning (`answer_sprint_hypothetical`).
        *   Changing issue status (`transition_issue_status`).
        *   Adding comments (`add_comment_to_issue`).
        *   Printing dependency graphs (`print_issue_dependency_graph`).
    *   **`tools`:** Exposes a set of Jira CPA-related functions:
        *   `FunctionTool(answer_jira_query)`
        *   `FunctionTool(what_is_blocking)`
        *   `FunctionTool(answer_sprint_hypothetical)`
        *   `FunctionTool(who_is_assigned)`
        *   `FunctionTool(transition_issue_status)`
        *   `FunctionTool(add_comment_to_issue)`
        *   `FunctionTool(print_issue_dependency_graph)`

#### `backend/agents/sub_agents/jira_sprint_agent/agent.py`

**Note:** This agent appears to be largely redundant with `backend/agents/sub_agents/jira_agent/agent.py`. Both have very similar descriptions and expose almost identical sets of tools related to Jira sprint summaries and issue overviews, including the memory-based default tools. This might indicate a refactoring opportunity or a historical artifact. For documentation purposes, I will treat it as a separate, but functionally overlapping, agent.

*   **`jira_sprint_agent`:**
    *   **Name:** "jira_sprint_agent"
    *   **Model:** `gemini-2.0-flash`
    *   **Description:** "Jira sub-agent handling sprint summaries and issue overviews."
    *   **Instruction:** Similar to `jira_agent`, it guides the agent to use memory-based tools if `project_key` is not provided, and explicit tools if it is.
    *   **`tools`:**
        *   `FunctionTool(summarize_current_sprint_v1)`
        *   `FunctionTool(summarize_issues_in_sprint_v1)`
        *   `FunctionTool(summarize_current_sprint_default)`
        *   `FunctionTool(summarize_issues_in_sprint_default)`
        *   `FunctionTool(get_issues_assigned_to_user)`
        *   `FunctionTool(get_issues_for_active_sprint_v1)`
        *   `FunctionTool(get_issues_for_active_sprint_default)`

### 5. Tools (`backend/tools/`)

This directory contains various utility functions that interact with external APIs (Jira, GitHub) or perform specific computations (CPA). These functions are designed to be called by the ADK agents or directly by FastAPI endpoints.

#### `backend/tools/cpa/engine/`

This sub-directory contains the core logic for Critical Path Analysis (CPA) and its integration with Jira data.

*   **`cpa.py`:**
    *   **`_topo_sort(nodes, edges)`:** Performs a topological sort on a directed acyclic graph (DAG). Used to order tasks for CPA calculations. Handles cycles by falling back to input order.
    *   **`_build_graph_with_assignees(project)`:** Builds a graph representation from a `ProjectModel`, including task nodes, successors, predecessors, durations, and assignees.
    *   **`_run_pert_rcpsp_calc(project)`:**
        *   Implements PERT (Program Evaluation and Review Technique) for basic critical path calculation based on dependencies.
        *   Extends with RCPSP (Resource-Constrained Project Scheduling Problem) for single-capacity resources (assignees). This means it considers assignee availability when scheduling tasks.
        *   Calculates Earliest Start (ES), Earliest Finish (EF), Latest Start (LS), Latest Finish (LF), and Slack for each task, both for plain PERT and resource-constrained scenarios.
        *   Identifies the critical path (tasks with zero slack).
    *   **`run_cpa(project_id)`:** Main function to execute CPA for a given project ID. It loads project data from the DB, runs the PERT/RCPSP calculation, and returns detailed results.
    *   **`get_critical_path(project_id)`:** Returns an ordered list of tasks on the critical path.
    *   **`get_task_slack(task_id)`:** Returns the slack for a specific task.
    *   **`get_project_duration(project_id)`:** Returns the overall project duration based on CPA.
    *   **`get_issue_finish_bounds(project_id, issue_id)`:** Returns the earliest and latest finish dates for a specific issue, considering resource constraints.
    *   **`summarize_current_sprint_cpa(project_key)`:** A high-level helper that refreshes Jira sprint data into the DB, runs CPA, and returns a concise summary (e.g., total tasks, critical tasks, project duration).

*   **`db.py`:**
    *   Provides helper functions for interacting with the database to store and update Jira-related data for CPA.
    *   **`_ensure_project(db, name)`:** Ensures a project exists in the `projects` table, inserting it if not present.
    *   **`_upsert_user(db, username)`:** Ensures a user exists in the `users` table, inserting if not present, and returns their user ID.
    *   **`_task_table_columns(db)`:** Retrieves column information for the `tasks` table.
    *   **`_upsert_task(db, project_id, task_id, name, est_duration, assignee, end_date)`:** Inserts or updates a task in the `tasks` table. It handles different assignee column types and ensures the assignee user exists.
    *   **`_replace_dependencies(db, project_id, task_id, depends_on)`:** Replaces existing dependencies for a task with a new set of dependencies.

*   **`jira.py`:**
    *   Handles fetching Jira data for the CPA engine and syncing it to the local database.
    *   **`_JIRA_CACHE`:** A lightweight in-memory cache to reduce repeated Jira API calls.
    *   **`_cached_current_sprint_issues(project_key, ttl_seconds)`:** Caches issues from the current active sprint.
    *   **`_jira_search_project_issues(project_key)`:** Fetches all issues for a Jira project using JQL.
    *   **`_jira_search_current_sprint_issues(project_key)`:** Fetches issues in the current active sprint.
    *   **`_get_task_duration(fields)`:** Derives a task's duration from Jira fields (prioritizes Story Points, then time estimates, else defaults to 1 day).
    *   **`_parse_dependencies(fields)`:** Extracts issue keys that an issue depends on from Jira's `issuelinks`.
    *   **`_parse_iso_date(d)`:** Parses ISO date strings into Python `date` objects.
    *   **`_extract_sprint_dates(issues)`:** Infers sprint start and end dates from issues within a sprint.
    *   **`refresh_from_jira(project_key)`:** Syncs all issues for a project from Jira into the local database.
    *   **`refresh_sprint_from_jira(project_key)`:** Syncs issues from the current active sprint into the local database.

*   **`project_graph.py`:**
    *   Provides functions for building and formatting dependency graphs.
    *   **`build_weighted_dependency_graph(project_key)`:** Builds a directed dependency graph for all issues in a Jira project, including task durations.
    *   **`format_dependency_graph(graph)`:** Formats the dependency graph into a human-readable string.
    *   **`print_dependency_graph_for_issue(issue_key)`:** A convenience helper to infer the project key from an issue key, build the project's dependency graph, and return its printable string representation.

*   **`sprint_dependency.py`:**
    *   Focuses on building and scheduling based on sprint dependencies and assignee availability.
    *   **`current_sprint_dependency_graph(project_key)`:** Builds a weighted dependency graph specifically for issues in the current sprint, including assignee, duration, and sprint-limited dependencies.
    *   **`format_current_sprint_dependency_graph(graph)`:** Formats the sprint dependency graph into a human-readable string.
    *   **`print_current_sprint_dependency_graph_for_issue(issue_key)`:** Prints the current sprint's dependency graph for a specific issue.
    *   **`schedule_current_sprint_with_dependencies(...)`:** Implements a resource-constrained scheduler for the current sprint. It respects task dependencies, assignee availability, working days, and holidays to determine per-issue start/end dates and overall sprint completion.
    *   **`expected_completion_for_issue_in_current_sprint(...)`:** Computes the expected completion date for a single issue within the current sprint using the RCPSP-like scheduler.

*   **`sprint_eta.py`:**
    *   Calculates optimistic and pessimistic ETA (Estimated Time of Arrival) for Jira issues within the current sprint.
    *   **`_detect_cycles(nodes)`:** Detects cycles in a dependency graph.
    *   **`_topo_order(nodes)`:** Performs a topological sort.
    *   **`_compute_ancestors_of_target(nodes, target)`:** Computes all ancestors of a target node in the graph.
    *   **`compute_eta_range_for_issue_current_sprint(...)`:**
        *   The core function for ETA calculation.
        *   Uses the sprint's dependency graph.
        *   Applies optional capacity scaling per user (e.g., if an assignee works fewer hours per day).
        *   Detects and reports cycles in the graph.
        *   Calculates an **optimistic schedule** (earliest possible completion, considering dependencies and assignee availability).
        *   Calculates a **pessimistic schedule** (delays the target by prioritizing non-ancestor tasks with longer durations).
        *   Returns a JSON object with optimistic/pessimistic days, schedules, critical paths, and blockers.

*   **`sprint_timeline.py`:**
    *   Provides functions for generating sprint timelines and simulating changes.
    *   **`_advance_working_days(start, days, working_days, holidays)`:** Helper to calculate a future date by advancing a specified number of working days, skipping weekends and holidays.
    *   **`_to_date_set(dates)`:** Converts a list of ISO date strings to a set of `date` objects.
    *   **`_next_working_day(d, working_days, holidays)`:** Returns the next working day from a given date.
    *   **`current_sprint_cpa_timeline(...)`:** Generates a detailed timeline for the current sprint. It groups tasks by assignee, schedules them sequentially for each assignee, and respects working days and holidays. Returns per-issue completion dates, per-assignee timelines, and overall sprint completion.
    *   **`sprint_completion_if_issue_removed(...)`:** Simulates the impact of removing a specific issue from the current sprint. It recomputes the sprint timeline without that issue and returns the "before" and "after" overall completion dates, along with the delta in days.
    *   **`estimate_issue_completion_in_current_sprint(...)`:** Provides a lightweight estimate for a single issue's completion. It only schedules tasks for the target assignee sequentially, minimizing computational load.

#### `backend/tools/github/repo_tools.py`

This module contains functions for interacting with the GitHub API.

*   **`list_repositories(organization)`:**
    *   Fetches a list of repositories for a given GitHub organization.
    *   Returns information about the latest changed repository (name, last pushed date).
    *   Requires `GITHUB_TOKEN` environment variable.
*   **`list_todays_commits(repo_full_name, branch)`:**
    *   Fetches all commits made today (in the local machine's timezone) for a specified GitHub repository and optional branch.
    *   Returns a human-readable string listing commit SHA, author, time, and message.
    *   Requires `GITHUB_TOKEN` environment variable.

#### `backend/tools/jira/`

This directory contains various modules for interacting with the Jira API, categorized by their functionality.

*   **`comment_tools.py`:**
    *   **`_jira_env()`:** Helper to read Jira environment variables (`JIRA_SERVER`, `JIRA_USERNAME`, `JIRA_API`) and validate their presence.
    *   **`add_comment_to_jira_issue(issue_key, comment_body)`:** Adds a comment to a specified Jira issue. Returns a success/error dictionary with comment details.

*   **`cpa_tools.py`:**
    *   Contains a mix of Jira interaction and CPA-related helper functions.
    *   **`_jira_env()`:** (Duplicate of the one in `comment_tools.py` and `sprint_tools.py`).
    *   **`_sp_field_key()`:** Returns the Jira custom field key for Story Points (configurable via `JIRA_STORY_POINTS_FIELD` env var, with a common default).
    *   **`_fetch_issue_details(issue_key)`:** Fetches comprehensive details for a Jira issue, including summary, status, assignee, due date, comments, and most importantly, **blockers** (parsed from `issuelinks`).
    *   **`_fetch_active_sprint_issues(project_key)`:** Fetches issues in the active sprint for a project, including simplified issue data and sprint information.
    *   **`answer_jira_query(issue_key, query)`:** Answers questions about a Jira issue using its details as context. It constructs a deterministic, concise answer based on available fields (summary, status, assignee, due date, comments, blockers). It explicitly states that an LLM-enabled agent can enrich this.
    *   **`what_is_blocking(issue_key)`:** Returns a human-readable list of issues blocking the given Jira issue, by querying issue links.
    *   **`answer_sprint_hypothetical(project_key, issue_key, query)`:** Answers hypothetical sprint planning questions (e.g., "if I move ISSUE-123 to next sprint"). It provides sprint info, remaining issues after exclusion, and assignee/status breakdowns, along with a projected completion date based on burn rate.
    *   **`who_is_assigned(issue_key)`:** Returns assignee information (name, email, avatar URL) for a Jira issue in a structured format.
    *   **`transition_issue_status(issue_key, new_status)`:** Transitions a Jira issue to a new status. It first fetches available transitions and then executes the desired one.
    *   **`add_comment_to_issue(issue_key, comment_body)`:** (Duplicate of `add_comment_to_jira_issue` in `comment_tools.py`).
    *   **`print_issue_dependency_graph(issue_key)`:** Calls the CPA engine tool to build and print the dependency graph for the issue's project.
    *   **`answer_when_issue_complete_range(issue_key, capacity_hours_per_user, workdays)`:** Returns the full JSON ETA range (optimistic-pessimistic) for an issue, using the CPA engine's `compute_eta_range_for_issue_current_sprint`.
    *   **`answer_when_issue_complete(issue_key, capacity_hours_per_user, workdays)`:** Returns a one-line human-readable answer for the ETA range.

*   **`hooks/commit_msg_hook.py`:**
    *   This is a Python script designed to be installed as a Git `commit-msg` hook.
    *   **Purpose:** Automatically transitions a referenced Jira issue to "In Review" (or other specified status) when a commit message contains the pattern `--issue <ISSUE_KEY>`.
    *   **Usage:** Executed by Git, it reads the commit message file.
    *   **Logic:** Uses a regular expression (`ISSUE_PATTERN`) to find issue keys and optional status flags (`--toProgress`, `--toDone`). It then calls `transition_issue_status` from `cpa_tools.py`.
    *   **Non-destructive:** Backs up existing hooks.
    *   **No LLMs:** This script is purely deterministic.

*   **`sprint_tools.py`:**
    *   Provides functions for fetching and summarizing Jira sprint data.
    *   **`_MEMORY`:** A lightweight in-process dictionary to remember the last used `project_key` and active `sprint` for "default" (no-arg) tools.
    *   **`_remember()` and `_recall_project_key()`, `_recall_active_sprint()`:** Functions for managing the in-module memory.
    *   **`_fetch_active_sprint(project_key)`:** Fetches the first active sprint for a given project and stores it in memory.
    *   **`_fetch_issues_in_active_sprint(project_key)`:** Fetches simplified issue data for the active sprint.
    *   **`summarize_current_sprint_default()`:** Summarizes the current sprint using the remembered `project_key`.
    *   **`summarize_issues_in_sprint_default()`:** Summarizes issues in the current sprint using the remembered `project_key`.
    *   **`summarize_current_sprint_v1(project_key)`:** Summarizes the current sprint for a given `project_key`. It attempts to use an internal ADK `Agent` (LLM) for a more natural summary, falling back to a deterministic summary if the LLM is unavailable or errors.
    *   **`summarize_issues_in_sprint_v1(project_key, max_results)`:** Summarizes issues in the current sprint. Similar to `summarize_current_sprint_v1`, it prefers an LLM-based summary but provides a deterministic fallback.
    *   **`get_issues_for_active_sprint_v1(project_key)`:** Retrieves a list of simplified issues for the active sprint.
    *   **`get_issues_for_active_sprint_default()`:** Retrieves issues for the active sprint using the remembered `project_key`.

*   **`user_issues_tools.py`:**
    *   **`_jira_env()`:** (Duplicate of the one in `comment_tools.py` and `sprint_tools.py`).
    *   **`get_issues_assigned_to_user(username)`:** Fetches all Jira issues assigned to a specific user. Returns a dictionary with a title and a list of simplified issue objects (key, summary, status, priority, URL).

### 6. Tests (`backend/tests/`)

This directory contains unit and integration tests for the backend components, ensuring their correctness and reliability.

*   **`conftest.py`:**
    *   Provides pytest fixtures for common test setup:
        *   `event_loop`: Asyncio event loop for asynchronous tests.
        *   `mock_env_vars`: Mocks environment variables (Jira, GitHub, JWT secrets, DB URL) for isolated testing.
        *   `test_db`: Creates a temporary SQLite database and overrides the `get_db` dependency in FastAPI, allowing tests to use an in-memory or file-based database.
        *   `mock_user`: Provides a mock authenticated user object.
        *   `authenticated_client`: A FastAPI `TestClient` pre-configured with an authenticated user.
        *   `client`: A basic FastAPI `TestClient`.
        *   `mock_runner`, `mock_session_service`: Mocks for Google ADK components to prevent actual LLM calls during tests.
        *   `mock_jira_response`, `mock_github_response`: Mocks for external API responses.
        *   `temp_state_file`: Creates a temporary file for testing workday state management.
        *   `mock_llm_calls`: An `autouse` fixture that patches ADK runners and session services globally for all tests, ensuring LLM calls are mocked by default.
        *   `mock_requests`: Mocks the `requests` library for controlling HTTP responses in tests.
*   **`test_agents.py`:**
    *   Tests the main orchestrating agent and its sub-agents.
    *   Verifies agent initialization, tool availability, and sub-agent integration.
    *   Includes tests for `who_is_assigned` tool, covering success, unassigned, not found, and missing environment variable scenarios.
    *   Confirms successful import of all sub-agents.
    *   Tests mocking of ADK agents and tools.
    *   Validates agent instruction content, warnings, and routing rules.
    *   Covers error handling for tools (network errors, timeouts, invalid input).
*   **`test_commands.py`:**
    *   Tests the CLI command handling logic in `app/commands.py`.
    *   Includes tests for `_extract_jira_key`, `_has_flag`, `_parse_repo_branch`.
    *   Verifies workday state file operations (`_save_workday_start`, `_load_workday_start`).
    *   Tests GitHub commits retrieval (`_github_commits_since`).
    *   Tests Jira-related helper functions (`_jira_auth_headers`, `_jira_count`, `_jira_summary_since`).
    *   Comprehensive tests for `handle_cli_commands`, covering `--start day` and `--end day` scenarios, including edge cases and missing state.
*   **`test_jira_eta_and_completion.py`:**
    *   Specifically tests the `/jira/issue-eta-graph` and `/jira/sprint-completion-if-removed` endpoints in `main.py`.
    *   Uses `monkeypatch` to inject fake CPA engine modules, ensuring these tests run without actual CPA calculations or external Jira calls.
    *   Verifies successful responses and error handling for invalid inputs.
*   **`test_main.py`:**
    *   Tests the core FastAPI endpoints and utility functions in `main.py`.
    *   Covers JWT encoding/decoding, token creation, and validation.
    *   Tests the in-memory Jira issue status cache.
    *   Verifies basic endpoints (`/`, `/debug/ping`).
    *   Extensive tests for authentication endpoints (`/login`, `/register`, `/auth/me`), including success, invalid credentials, user not found, and existing user scenarios.
    *   Tests the `/codinator/run-agent` endpoint, including successful agent runs, empty prompts, and pre-filtering logic for Jira status and ETA queries.
    *   Tests Jira-related endpoints (`/jira/issue-status`, `/jira/sprint-status`, `/jira/base-url`), covering success, not found, and unauthorized access.
    *   Includes error handling tests for agent timeouts and empty responses.

### 7. Configuration (`backend/pyproject.toml`, `backend/pytest.ini`)

These files define the project's metadata, dependencies, and testing configuration.

#### `backend/pyproject.toml`

*   **`[project]`:**
    *   `name = "backend"`
    *   `version = "0.1.0"`
    *   `description`: "Add your description here" (Placeholder, should be updated).
    *   `requires-python = ">=3.12"`
    *   **`dependencies`:** Lists all Python packages required by the backend, including:
        *   `google-adk`: The Agent Development Kit.
        *   `fastapi`, `uvicorn`: Web framework and ASGI server.
        *   `sqlalchemy`, `psycopg2-binary`, `alembic`: Database ORM, PostgreSQL driver, and database migrations.
        *   `passlib`, `bcrypt`, `python-jose`: Password hashing and JWT.
        *   `jira`: Python client for Jira API.
        *   `requests`, `python-dotenv`, `anyio`: HTTP requests, environment variable loading, async I/O.
        *   `pytest`, `pytest-cov`, `pytest-asyncio`, `pytest-mock`, `httpx`, `respx`: Testing frameworks and utilities.
        *   `litellm`, `google-generativeai`, `groq`: LLM integration.
        *   `pydantic-settings`: For settings management.
        *   `yfinance`, `psutil`, `vercel-ai`: Other specific libraries, their usage might be in other parts of the code not fully explored yet.
*   **`[tool.setuptools.packages.find]`:** Configures how `setuptools` finds packages within the project.

#### `backend/pytest.ini`

*   **`[tool:pytest]`:** Configures the `pytest` test runner.
    *   `testpaths = tests`: Specifies that tests are located in the `tests` directory.
    *   `python_files = test_*.py`: Matches test files starting with `test_`.
    *   `python_classes = Test*`: Matches test classes starting with `Test`.
    *   `python_functions = test_*`: Matches test functions starting with `test_`.
    *   `addopts`: Additional command-line options for pytest, including:
        *   `--verbose`: More detailed test output.
        *   `--tb=short`: Short traceback format.
        *   `--cov=.`: Enables code coverage for the entire project.
        *   `--cov-report=html:htmlcov`, `--cov-report=term-missing`: HTML and terminal reports for coverage.
        *   `--cov-fail-under=90`: Fails tests if coverage is below 90%.
        *   `--ignore`: Ignores specified directories (`.venv`, `__pycache__`, `.pytest_cache`).
    *   `filterwarnings`: Ignores specific deprecation warnings during tests.
    *   `markers`: Defines custom markers for categorizing tests (e.g., `unit`, `integration`, `slow`).

---
**Frontend Documentation**

### 1. Project Setup

The frontend is a modern web application built with:

*   **React:** A JavaScript library for building user interfaces.
*   **TypeScript:** A superset of JavaScript that adds static typing.
*   **Vite:** A fast build tool that provides a lightning-fast development experience with Hot Module Replacement (HMR).
*   **Tailwind CSS:** A utility-first CSS framework for rapidly styling components.

### 2. Main Application (`frontend/web/src/main.tsx`, `frontend/web/src/App.tsx`)

These files define the entry point and the main structure of the React application.

#### `frontend/web/src/main.tsx`

*   **Entry Point:** This is the main entry file for the React application.
*   **React Root:** Renders the main React application into the HTML element with `id="root"`.
*   **Strict Mode:** Wraps the application in `StrictMode` for highlighting potential problems in an application.
*   **React Router DOM:** Sets up client-side routing using `BrowserRouter`, `Routes`, and `Route` components.
*   **Authentication Flow:**
    *   `isAuthenticated()`: A simple check that verifies the presence of an `access_token` in `localStorage` to determine if a user is authenticated.
    *   `PrivateRoute`: A custom component that acts as a guard. If the user is not authenticated, it redirects them to the `/login` page; otherwise, it renders its children.
    *   **Routes:**
        *   `/login`: Renders the `LoginPage`.
        *   `/register`: Renders the `RegisterPage`.
        *   `/dashboard`: Renders the `DashboardPage`, protected by `PrivateRoute`.
        *   `/`: Redirects to `/login` by default.

#### `frontend/web/src/App.tsx`

*   **Root Component:** This is the main application component.
*   **Basic UI:** Displays Vite and React logos, a simple counter, and instructions for HMR.
*   **Styling:** Uses Tailwind CSS classes for layout and appearance, with custom theme variables defined in `index.css`.
*   **`ChatBox` Integration:** Includes the `ChatBox` component, which is the primary interactive element for communicating with the backend agents.

### 3. Components (`frontend/web/src/components/`)

This directory contains reusable React components that form the building blocks of the user interface. Many of these components are designed to render specific UI directives received from the backend's `formatter_agent`.

#### `frontend/web/src/components/ChatBox.tsx`

This is the central chat interface component, responsible for sending user input to the backend and rendering the responses.

*   **State Management:** Manages chat messages (`messages`), current input (`input`), and loading state (`loading`).
*   **API Interaction:**
    *   `API_BASE`: Configured via Vite environment variables (`VITE_API_BASE`).
    *   `coreSend(text)`: The core function for sending user prompts to the backend's `/codinator/run-agent` endpoint.
    *   **UI Directive Handling:** After receiving a response from the backend, it parses the JSON to identify specific UI directives (`ui` or `type` fields).
    *   **Dynamic Component Rendering:** Based on the `uiType` received, it dynamically renders the appropriate component (e.g., `JiraStatus`, `UserCard`, `IssueList`, `EtaEstimate`, `SprintSummary`, `WorkdaySummary`).
    *   **Backend-Driven UI:** This component demonstrates a "backend-driven UI" pattern, where the backend dictates how the frontend should render certain types of information.
    *   **Jira API Calls (Frontend-Initiated):** For `jira_status` and `eta_estimate` UI types, the `ChatBox` makes *additional* API calls to specific Jira endpoints (`/jira/issue-status`, `/jira/issue-eta-graph`) to fetch the detailed data required by the respective UI components. This suggests a hybrid approach where some data fetching is offloaded to the frontend after the initial agent response.
    *   **Jira Base URL Fetch:** On mount, it attempts to fetch and cache the Jira base URL from `/jira/base-url` for constructing deep links.
    *   **Workday Summary Parsing:** Contains client-side logic to parse the raw text output of `--start day` and `--end day` commands into a structured format for the `WorkdaySummary` component.
*   **Input Handling:** Manages the text input field and sends messages on Enter key press.
*   **`useImperativeHandle`:** Exposes `sendContent` and `insertText` methods to parent components, allowing programmatic interaction with the chatbox.

#### `frontend/web/src/components/EtaEstimate.tsx`

*   **Purpose:** Displays estimated time of arrival (ETA) and dependency graph information for a Jira issue.
*   **`EtaEstimateData`:** Defines the expected data structure, including optimistic/pessimistic days, critical paths, blockers, and a graph of nodes (tasks with assignees, durations, and dependencies).
*   **Visuals:** Uses `framer-motion` for animations and a "futuristic neon" theme.
*   **`Tree` Component:** A recursive helper component to render the dependency graph visually.
*   **Progress Bars:** Visualizes optimistic and pessimistic ETA using animated progress bars.

#### `frontend/web/src/components/IssueList.tsx`

*   **Purpose:** Renders a list of Jira issues.
*   **`IssueListData`:** Defines the data structure, including an optional title and an array of `IssueListItem` objects.
*   **`IssueListItem`:** Represents a single issue with key, summary, status, priority, and URL.
*   **Visuals:** Uses `framer-motion` for list item animations.
*   **Jira Links:** Constructs clickable links to Jira issues using the cached Jira base URL.

#### `frontend/web/src/components/JiraStatus.tsx`

*   **Purpose:** Displays the status and details of a single Jira issue.
*   **`JiraStatusData`:** Defines the data structure, including issue key, name (summary), expected finish date, status, and comments.
*   **Visuals:** Uses `framer-motion` for animations and a neon-themed design.
*   **Jira Link:** Provides a clickable link to the Jira issue.
*   **Comments Display:** Lists recent comments for the issue.

#### `frontend/web/src/components/SprintStatus.tsx`

*   **Purpose:** Displays the status and progress of a Jira sprint.
*   **`SprintStatusData`:** Defines the data structure, including sprint name, start/end dates, notes, total issues, and completed issues.
*   **Visuals:** Shows sprint name, dates, issue counts, and a progress bar for completion percentage.

#### `frontend/web/src/components/SprintSummary.tsx`

*   **Purpose:** Provides a high-level summary of a Jira sprint.
*   **`SprintSummaryData`:** Defines the data structure, including project key, total issues, status category counts, sample issues, sprint name, and dates.
*   **Visuals:** Displays key metrics, status breakdowns, and a sample of issues.
*   **Jira Links:** Sample issues are clickable links to Jira.

#### `frontend/web/src/components/UserCard.tsx`

*   **Purpose:** Displays information about a user, typically an assignee of a Jira issue.
*   **`UserCardData`:** Defines the data structure, including name, designation, email, avatar URL, and online status.
*   **Visuals:** Uses `framer-motion` for animations, displays an avatar (or a generated one), and indicates online/offline status.
*   **Jira Link:** Provides a clickable link to Jira issues assigned to the user.

#### `frontend/web/src/components/WorkdaySummary.tsx`

*   **Purpose:** Renders summaries for workday start and end commands.
*   **`WorkdaySummaryData`:** Defines the data structure, which can be in 'start' mode (showing tasks due today, next up) or 'end' mode (showing Jira activity and GitHub commits since start).
*   **Visuals:** Formats and displays the relevant information based on the `mode`.
For GitHub commits, it uses a `pre` tag for formatted text.

### 4. Pages (`frontend/web/src/pages/`)

These components represent full-page views in the application.

#### `frontend/web/src/pages/DashboardPage.tsx`

*   **Purpose:** The main dashboard view after successful login.
*   **Content:** Currently, it primarily hosts the `ChatBox` component.

#### `frontend/web/src/pages/LoginPage.tsx`

*   **Purpose:** Provides a user login interface.
*   **State:** Manages `username`, `password`, and `message` (for feedback).
*   **API Interaction:** Sends login credentials to the backend's `/login` endpoint.
*   **Authentication:** On successful login, it stores the `access_token` in `localStorage` and redirects to the `/dashboard`.
*   **Navigation:** Uses `useNavigate` from `react-router-dom` for programmatic navigation.

#### `frontend/web/src/pages/RegisterPage.tsx`

*   **Purpose:** Provides a user registration interface.
*   **State:** Manages `username`, `password`, and `message`.
*   **API Interaction:** Sends registration details to the backend's `/register` endpoint.
*   **Navigation:** On successful registration, it redirects to the `/login` page.

### 5. Styling (`frontend/web/src/index.css`)

*   **Tailwind CSS:** Imports Tailwind CSS, which provides utility classes for styling.
*   **Custom Theme:** Defines a custom `@theme` block with:
    *   **`--color-primary-*`:** Futuristic neon purple color palette.
    *   **`--color-secondary-*`:** Dark gray background palette.
    *   **`--color-accent-*`:** Electric cyan, neon pink, neon green, and neon yellow accent colors.
    *   **Fonts:** Defines custom font families (`Orbitron`, `JetBrains Mono`, `Audiowide`) for a futuristic look.
    *   **Spacing Scale:** Custom spacing variables.
*   **Custom Components (`@layer components`):** Defines reusable component styles (e.g., `.btn`, `.input`, `.badge`, `.alert`) using Tailwind's `@apply` directive and custom CSS properties for colors and shadows, creating a consistent "futuristic neon" design language.
*   **Animations:** Includes a `fadeIn` keyframe animation.

### 6. Configuration (`frontend/web/package.json`, `frontend/web/vite.config.ts`, `frontend/web/tsconfig.*.json`)

These files configure the frontend development environment, build process, and TypeScript settings.

#### `frontend/web/package.json`

*   **`name`: "web"**
*   **`private`: true**
*   **`version`: "0.0.0"**
*   **`type`: "module"**
*   **`scripts`:**
    *   `dev`: Starts the Vite development server.
    *   `build`: Compiles TypeScript and builds the production-ready application.
    *   `lint`: Runs ESLint for code linting.
    *   `preview`: Serves the production build locally.
*   **`dependencies`:** Lists runtime dependencies:
    *   `framer-motion`: For animations.
    *   `react`, `react-dom`: React core libraries.
    *   `react-router-dom`: For client-side routing.
*   **`devDependencies`:** Lists development dependencies:
    *   `@eslint/js`, `eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `globals`, `typescript-eslint`: ESLint and TypeScript ESLint configuration.
    *   `@tailwindcss/vite`, `tailwindcss`: Tailwind CSS integration for Vite.
    *   `@types/react`, `@types/react-dom`: TypeScript type definitions for React.
    *   `@vitejs/plugin-react`, `vite`: Vite plugin for React and the Vite build tool itself.
    *   `typescript`: TypeScript compiler.

#### `frontend/web/vite.config.ts`

*   **Vite Configuration:** Defines how Vite builds and serves the application.
*   **Plugins:**
    *   `react()`: Enables React support with Vite.
    *   `tailwindcss()`: Integrates Tailwind CSS with Vite.

#### `frontend/web/tsconfig.app.json`

*   **TypeScript Configuration (Application):** Specific settings for compiling the main application source code.
    *   `target`, `lib`, `module`: JavaScript target version, standard libraries, and module system.
    *   `jsx`: Set to `react-jsx` for React's new JSX transform.
    *   `strict`, `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`: Strictness and code quality checks.
    *   `include`: Specifies the `src` directory for compilation.

#### `frontend/web/tsconfig.node.json`

*   **TypeScript Configuration (Node.js environment):** Specific settings for TypeScript files that run in a Node.js environment (e.g., Vite configuration files).
    *   Similar compiler options to `tsconfig.app.json` but tailored for Node.js.
    *   `include`: Specifies `vite.config.ts`.

#### `frontend/web/tsconfig.json`

*   **Project References:** A root `tsconfig.json` that references `tsconfig.app.json` and `tsconfig.node.json`, allowing for a monorepo-like setup and better build performance.

---
