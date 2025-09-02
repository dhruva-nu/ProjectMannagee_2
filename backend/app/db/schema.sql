CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE tasks (
    id VARCHAR(50) PRIMARY KEY,          -- Jira issue key or custom ID
    project_id INT REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    estimate_days FLOAT NOT NULL,
    start_date DATE,
    end_date DATE,
    assignee TEXT
);

CREATE TABLE dependencies (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(50) REFERENCES tasks(id) ON DELETE CASCADE,
    depends_on VARCHAR(50) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    skills jsonb DEFAULT '{}'::jsonb
);

ALTER TABLE tasks DROP COLUMN assignee;

ALTER TABLE tasks
ADD COLUMN assignee INT REFERENCES users(id) ON DELETE SET NULL;
