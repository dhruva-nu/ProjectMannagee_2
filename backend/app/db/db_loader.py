from models import TaskModel, ProjectModel
from dotenv import load_dotenv

load_dotenv()

def load_project_from_db(session, project_id: int) -> ProjectModel:
    task_rows = session.execute("""
        SELECT id, name, estimate_days, start_date, end_date, assignee
        FROM tasks WHERE project_id = :pid
    """, {"pid": project_id}).fetchall()

    dep_rows = session.execute("""
        SELECT task_id, depends_on 
        FROM dependencies
        JOIN tasks t ON t.id = dependencies.task_id
        WHERE t.project_id = :pid
    """, {"pid": project_id}).fetchall()

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

