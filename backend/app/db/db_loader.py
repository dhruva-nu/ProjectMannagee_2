from .models import TaskModel, ProjectModel
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

def load_project_from_db(session, project_id: int) -> ProjectModel:
    # Inspect tasks table columns to normalize assignee to username (string)
    cols = session.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'tasks'
    """)).fetchall()
    colmap = {r.column_name: r.data_type for r in cols}

    if 'assignee_id' in colmap:
        # Standard FK to users.id
        task_rows = session.execute(text("""
            SELECT t.id, t.name, t.estimate_days, t.start_date, t.end_date,
                   u.username AS assignee
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assignee_id
            WHERE t.project_id = :pid
        """), {"pid": project_id}).fetchall()
    elif colmap.get('assignee') == 'integer':
        # Integer assignee column stores user id
        task_rows = session.execute(text("""
            SELECT t.id, t.name, t.estimate_days, t.start_date, t.end_date,
                   COALESCE(u.username, t.assignee::text) AS assignee
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assignee
            WHERE t.project_id = :pid
        """), {"pid": project_id}).fetchall()
    elif 'assignee' in colmap:
        # Text assignee already stores username
        task_rows = session.execute(text("""
            SELECT id, name, estimate_days, start_date, end_date, assignee
            FROM tasks WHERE project_id = :pid
        """), {"pid": project_id}).fetchall()
    else:
        # No assignee column
        task_rows = session.execute(text("""
            SELECT id, name, estimate_days, start_date, end_date, NULL::text AS assignee
            FROM tasks WHERE project_id = :pid
        """), {"pid": project_id}).fetchall()

    dep_rows = session.execute(text("""
        SELECT task_id, depends_on 
        FROM dependencies
        JOIN tasks t ON t.id = dependencies.task_id
        WHERE t.project_id = :pid
    """), {"pid": project_id}).fetchall()

    dep_map = {}
    for dep in dep_rows:
        dep_map.setdefault(dep.task_id, []).append(dep.depends_on)

    tasks = []
    for row in task_rows:
        tasks.append(TaskModel(
            id=row.id,
            name=row.name,
            estimate_days=row.estimate_days,
            start_date=row.start_date,
            end_date=row.end_date,
            assignee=row.assignee,
            dependencies=dep_map.get(row.id, [])
        ))

    return ProjectModel(id=project_id, name=f"Project {project_id}", tasks=tasks)

