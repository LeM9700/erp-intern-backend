from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_admin, require_intern
from app.db.session import get_db
from app.models.user import User
from app.schemas.pagination import paginate_meta
from app.schemas.task import (
    TaskCommentCreate, TaskCommentListOut, TaskCommentOut,
    TaskCreate, TaskListOut, TaskOut, TaskUpdate,
)
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# ── ADMIN routes ──

@router.post("", response_model=list[TaskOut], status_code=201)
async def create_task(
    body: TaskCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await TaskService.create_task(db, body, admin.id)


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: str,
    body: TaskUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await TaskService.update_task(db, task_id, body)


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await TaskService.delete_task(db, task_id)


@router.get("/admin", response_model=TaskListOut)
async def list_admin_tasks(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    tasks, total = await TaskService.list_admin_tasks(db, page=page, size=size)
    return TaskListOut(
        items=tasks,
        **paginate_meta(total, page, size).model_dump(),
    )


# ── INTERN routes ──

@router.get("/me", response_model=TaskListOut)
async def list_my_tasks(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    intern: User = Depends(require_intern),
    db: AsyncSession = Depends(get_db),
):
    tasks, total = await TaskService.list_intern_tasks(db, intern.id, page=page, size=size)
    return TaskListOut(
        items=tasks,
        **paginate_meta(total, page, size).model_dump(),
    )


@router.patch("/{task_id}/start", response_model=TaskOut)
async def start_task(
    task_id: str,
    intern: User = Depends(require_intern),
    db: AsyncSession = Depends(get_db),
):
    return await TaskService.start_task(db, task_id, intern.id)


@router.post("/{task_id}/submit", response_model=TaskOut)
async def submit_task(
    task_id: str,
    note: str = Form(...),
    proof_file: UploadFile | None = File(None),
    proof_url: str | None = Form(None),
    intern: User = Depends(require_intern),
    db: AsyncSession = Depends(get_db),
):
    return await TaskService.submit_task(
        db, task_id, intern.id, note,
        proof_file=proof_file or None,
        proof_url=proof_url or None,
    )


# ── COMMENT routes (any authenticated user) ──

@router.post("/{task_id}/comments", response_model=TaskCommentOut, status_code=201)
async def add_comment(
    task_id: str,
    body: TaskCommentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TaskService.add_comment(db, task_id, user.id, body.content)


@router.get("/{task_id}/comments", response_model=TaskCommentListOut)
async def list_comments(
    task_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    comments, total = await TaskService.list_comments(db, task_id, page=page, size=size)
    return TaskCommentListOut(
        items=comments,
        **paginate_meta(total, page, size).model_dump(),
    )


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await TaskService.delete_comment(db, comment_id, user.id)
