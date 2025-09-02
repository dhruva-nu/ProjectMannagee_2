from typing import List, Optional
from pydantic import BaseModel
from datetime import date


class DependencyModel(BaseModel):
    task_id: str
    depends_on: str


class TaskModel(BaseModel):
    id: str
    name: str
    estimate_days: float
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    assignee: Optional[str] = None
    dependencies: List[str] = []


class ProjectModel(BaseModel):
    id: int
    name: str
    tasks: List[TaskModel] = []
