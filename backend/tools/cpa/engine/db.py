import json
from datetime import datetime
from typing import Optional, List

from sqlalchemy import text
from sqlalchemy.orm import Session


# ------------------------------
# DB upsert helpers
# ------------------------------

def _ensure_project(db: Session, name: str) -> int:
    row = db.execute(text("""
        SELECT id FROM projects WHERE name = :name
    """), {"name": name}).fetchone()
    if row:
        return int(row.id)
    new_row = db.execute(text("""
        INSERT INTO projects (name) VALUES (:name)
        RETURNING id
    """), {"name": name}).fetchone()
    db.commit()
    return int(new_row.id)


def _upsert_user(db: Session, username: str) -> Optional[int]:
    """Ensure user exists; return user id if available, else None."""
    if not username:
        return None
    try:
        row = db.execute(text("""
            SELECT id FROM users WHERE username = :u
        """), {"u": username}).fetchone()
        if row:
            return int(row.id)
        # Insert with empty password and empty skills JSONB
        new_row = db.execute(text("""
            INSERT INTO users (username, hashed_password, skills)
            VALUES (:u, :hp, :skills)
            RETURNING id
        """), {"u": username, "hp": "", "skills": json.dumps({})}).fetchone()
        db.commit()
        return int(new_row.id) if new_row else None
    except Exception:
        # Best-effort; do not fail refresh if users table has constraints
        db.rollback()
        return None


def _task_table_columns(db: Session) -> dict:
    """Return mapping of column_name -> data_type for 'tasks' table."""
    rows = db.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'tasks'
    """)).fetchall()
    return {r.column_name: r.data_type for r in rows}


def _upsert_task(db: Session, project_id: int, task_id: str, name: str, est_duration: float,
                 assignee: Optional[str], end_date: Optional[str]):
    # Normalize date to date string if present
    end_dt_sql = None
    if end_date:
        try:
            end_dt_sql = datetime.fromisoformat(end_date.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            end_dt_sql = None
    cols = _task_table_columns(db)
    has_assignee_id = 'assignee_id' in cols
    has_assignee = 'assignee' in cols
    assignee_is_int = (cols.get('assignee') == 'integer') if has_assignee else False

    user_id: Optional[int] = None
    if assignee and (has_assignee_id or assignee_is_int):
        user_id = _upsert_user(db, assignee)

    if has_assignee_id:
        db.execute(text("""
            INSERT INTO tasks (id, project_id, name, estimate_days, end_date, assignee_id)
            VALUES (:id, :pid, :name, :est_duration, :end_date, :assignee_id)
            ON CONFLICT (id) DO UPDATE SET
              project_id = EXCLUDED.project_id,
              name = EXCLUDED.name,
              estimate_days = EXCLUDED.estimate_days,
              end_date = EXCLUDED.end_date,
              assignee_id = EXCLUDED.assignee_id
        """), {
            "id": task_id,
            "pid": project_id,
            "name": name or task_id,
            "est_duration": float(est_duration or 1.0),
            "end_date": end_dt_sql,
            "assignee_id": user_id,
        })
    elif has_assignee and assignee_is_int:
        db.execute(text("""
            INSERT INTO tasks (id, project_id, name, estimate_days, end_date, assignee)
            VALUES (:id, :pid, :name, :est_duration, :end_date, :assignee)
            ON CONFLICT (id) DO UPDATE SET
              project_id = EXCLUDED.project_id,
              name = EXCLUDED.name,
              estimate_days = EXCLUDED.estimate_days,
              end_date = EXCLUDED.end_date,
              assignee = EXCLUDED.assignee
        """), {
            "id": task_id,
            "pid": project_id,
            "name": name or task_id,
            "est_duration": float(est_duration or 1.0),
            "end_date": end_dt_sql,
            "assignee": user_id,
        })
    elif has_assignee:
        db.execute(text("""
            INSERT INTO tasks (id, project_id, name, estimate_days, end_date, assignee)
            VALUES (:id, :pid, :name, :est_duration, :end_date, :assignee)
            ON CONFLICT (id) DO UPDATE SET
              project_id = EXCLUDED.project_id,
              name = EXCLUDED.name,
              estimate_days = EXCLUDED.estimate_days,
              end_date = EXCLUDED.end_date,
              assignee = EXCLUDED.assignee
        """), {
            "id": task_id,
            "pid": project_id,
            "name": name or task_id,
            "est_duration": float(est_duration or 1.0),
            "end_date": end_dt_sql,
            "assignee": assignee,
        })
    else:
        db.execute(text("""
            INSERT INTO tasks (id, project_id, name, estimate_days, end_date)
            VALUES (:id, :pid, :name, :est_duration, :end_date)
            ON CONFLICT (id) DO UPDATE SET
              project_id = EXCLUDED.project_id,
              name = EXCLUDED.name,
              estimate_days = EXCLUDED.estimate_days,
              end_date = EXCLUDED.end_date
        """), {
            "id": task_id,
            "pid": project_id,
            "name": name or task_id,
            "est_duration": float(est_duration or 1.0),
            "end_date": end_dt_sql,
        })


def _replace_dependencies(db: Session, task_id: str, depends_on: List[str]):
    # Clear existing, then insert
    db.execute(text("""
        DELETE FROM dependencies WHERE task_id = :tid
    """), {"tid": task_id})
    for dep in depends_on:
        if dep and dep != task_id:
            db.execute(text("""
                INSERT INTO dependencies (task_id, depends_on) VALUES (:tid, :dep)
                ON CONFLICT DO NOTHING
            """), {"tid": task_id, "dep": dep})
