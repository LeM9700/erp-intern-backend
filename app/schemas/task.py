from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

from app.models.task import TaskStatus, TaskPriority


# ── Input ──
class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_to: list[UUID] | None = None
    due_date: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: TaskPriority | None = None
    assigned_to: UUID | None = None
    due_date: datetime | None = None
    status: TaskStatus | None = None


# ── Output ──
class TaskProofOut(BaseModel):
    id: UUID
    file_id: UUID | None
    proof_url: str | None = None
    note: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskOut(BaseModel):
    id: UUID
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    assigned_to: UUID | None
    created_by: UUID
    due_date: datetime | None
    started_at: datetime | None
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    proofs: list[TaskProofOut] = []

    model_config = {"from_attributes": True}


class TaskListOut(BaseModel):
    items: list[TaskOut]
    total: int
    page: int
    size: int
    pages: int


# ── Task Comments ──
class TaskCommentCreate(BaseModel):
    content: str


class TaskCommentOut(BaseModel):
    id: UUID
    task_id: UUID
    author_id: UUID
    author_full_name: str = ""
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskCommentListOut(BaseModel):
    items: list[TaskCommentOut]
    total: int
    page: int
    size: int
    pages: int
