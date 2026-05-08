CREATE TABLE IF NOT EXISTS tasks (
    task_id        TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL,
    source_agent   TEXT NOT NULL,
    target_agent   TEXT NOT NULL,
    state          TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(state);

CREATE TABLE IF NOT EXISTS messages (
    message_id     TEXT PRIMARY KEY,
    task_id        TEXT NOT NULL,
    role           TEXT NOT NULL,
    parts_json     TEXT NOT NULL,
    timestamp      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_task ON messages(task_id);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id    TEXT PRIMARY KEY,
    task_id        TEXT NOT NULL,
    name           TEXT NOT NULL,
    parts_json     TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id     TEXT PRIMARY KEY,
    user_query     TEXT NOT NULL,
    final_report   TEXT,
    risk_level     TEXT,
    started_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at   TIMESTAMP
);
