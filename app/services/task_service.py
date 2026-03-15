import uuid
import re
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.activity import ActivityAction
from app.models.file import File
from app.models.notification import Notification
from app.models.task import Task, TaskProof, TaskComment, TaskStatus
from app.models.user import User, UserRole
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.activity_service import ActivityLogService
from app.services.storage import StorageService

MAX_PROOF_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
ALLOWED_PROOF_TYPES = {
    "image/jpeg", "image/png", "image/webp",
    "application/pdf",
    "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/zip",
    "application/x-zip-compressed",
}
_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


class TaskService:

    @staticmethod
    async def create_task(
        db: AsyncSession, data: TaskCreate, created_by: uuid.UUID
    ) -> list[Task]:
        assignees: list[uuid.UUID | None] = data.assigned_to if data.assigned_to else [None]
        tasks: list[Task] = []
        for assignee in assignees:
            task = Task(
                title=data.title,
                description=data.description,
                priority=data.priority,
                assigned_to=assignee,
                created_by=created_by,
                due_date=data.due_date,
            )
            db.add(task)
            await db.flush()
            await db.refresh(task, ["proofs", "reviews"])

            if assignee:
                db.add(Notification(
                    user_id=assignee,
                    title="Nouvelle tâche assignée",
                    message=f"La tâche '{task.title}' vous a été assignée.",
                ))
                await db.flush()

            tasks.append(task)
        return tasks

    @staticmethod
    async def update_task(
        db: AsyncSession, task_id: uuid.UUID, data: TaskUpdate
    ) -> Task:
        result = await db.execute(
            select(Task)
            .options(selectinload(Task.proofs), selectinload(Task.reviews))
            .where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        if task.status == TaskStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot modify an approved task",
            )

        update_fields = data.model_dump(exclude_unset=True)
        new_status = update_fields.get("status")
        old_assigned = task.assigned_to
        new_assigned = update_fields.get("assigned_to")

        for field, value in update_fields.items():
            setattr(task, field, value)

        await db.flush()
        await db.refresh(task, ["proofs", "reviews"])

        # Notification si ré-assignation à un nouveau stagiaire
        if new_assigned and new_assigned != old_assigned:
            db.add(Notification(
                user_id=new_assigned,
                title="Nouvelle tâche assignée",
                message=f"La tâche '{task.title}' vous a été assignée.",
            ))
            await db.flush()

        # Notify the assigned intern when their task is approved or rejected
        if new_status in (TaskStatus.APPROVED, TaskStatus.REJECTED) and task.assigned_to:
            status_label = "approuvée" if new_status == TaskStatus.APPROVED else "rejetée"
            notification = Notification(
                user_id=task.assigned_to,
                title=f"Tâche {status_label}",
                message=f"Votre tâche '{task.title}' a été {status_label}.",
            )
            db.add(notification)
            await db.flush()

        return task

    @staticmethod
    async def list_admin_tasks(
        db: AsyncSession, page: int = 1, size: int = 20
    ) -> tuple[list[Task], int]:
        total = (await db.execute(
            select(func.count()).select_from(Task)
        )).scalar() or 0
        result = await db.execute(
            select(Task)
            .options(selectinload(Task.proofs), selectinload(Task.reviews))
            .order_by(Task.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def list_intern_tasks(
        db: AsyncSession, user_id: uuid.UUID, page: int = 1, size: int = 20
    ) -> tuple[list[Task], int]:
        base = Task.assigned_to == user_id
        total = (await db.execute(
            select(func.count()).select_from(Task).where(base)
        )).scalar() or 0
        result = await db.execute(
            select(Task)
            .options(selectinload(Task.proofs), selectinload(Task.reviews))
            .where(base)
            .order_by(Task.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def start_task(
        db: AsyncSession, task_id: uuid.UUID, user_id: uuid.UUID
    ) -> Task:
        result = await db.execute(
            select(Task)
            .options(selectinload(Task.proofs), selectinload(Task.reviews))
            .where(Task.id == task_id, Task.assigned_to == user_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        if task.status == TaskStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot modify an approved task",
            )

        if task.status != TaskStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task can only be started from PENDING status",
            )

        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(task, ["proofs", "reviews"])

        await ActivityLogService.log(
            db,
            user_id=user_id,
            action=ActivityAction.TASK_START,
            entity_id=task.id,
            entity_type="Task",
            detail=f"Started task: {task.title}",
        )

        return task

    @staticmethod
    async def submit_task(
        db: AsyncSession,
        task_id: uuid.UUID,
        user_id: uuid.UUID,
        note: str,
        proof_file: UploadFile | None = None,
        proof_url: str | None = None,
    ) -> Task:
        # Validate: exactly one proof source
        if not proof_file and not proof_url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Vous devez fournir un fichier ou un lien comme preuve.",
            )
        if proof_file and proof_url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Fournissez soit un fichier, soit un lien — pas les deux.",
            )

        # Validate URL format
        if proof_url and not _URL_RE.match(proof_url):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Le lien doit commencer par http:// ou https://",
            )

        result = await db.execute(
            select(Task)
            .options(selectinload(Task.proofs), selectinload(Task.reviews))
            .where(Task.id == task_id, Task.assigned_to == user_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        if task.status == TaskStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot modify an approved task",
            )

        if task.status not in (TaskStatus.IN_PROGRESS, TaskStatus.REJECTED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task must be IN_PROGRESS or REJECTED to submit",
            )

        # Handle file upload
        file_id: uuid.UUID | None = None
        if proof_file:
            content_type = proof_file.content_type or ""
            if content_type not in ALLOWED_PROOF_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Type de fichier non autorisé : {content_type}",
                )
            meta = await StorageService.save_upload_locally(proof_file, user_id, "task_proofs")
            if meta["size_bytes"] > MAX_PROOF_FILE_SIZE:
                StorageService.delete_local_file(meta["stored_path"])
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Fichier trop volumineux (max 20 Mo).",
                )
            db_file = File(
                original_filename=meta["original_filename"],
                stored_path=meta["stored_path"],
                mime_type=meta["mime_type"],
                size_bytes=meta["size_bytes"],
                uploaded_by=user_id,
                confirmed=True,
            )
            db.add(db_file)
            await db.flush()
            file_id = db_file.id

        # Create proof
        proof = TaskProof(task_id=task.id, file_id=file_id, proof_url=proof_url, note=note)
        db.add(proof)

        task.status = TaskStatus.SUBMITTED
        task.submitted_at = datetime.now(timezone.utc)
        await db.flush()

        # Refresh to load proofs/reviews
        await db.refresh(task, ["proofs", "reviews"])

        # Log
        await ActivityLogService.log(
            db,
            user_id=user_id,
            action=ActivityAction.TASK_SUBMIT,
            entity_id=task.id,
            entity_type="Task",
            detail=f"Submitted task: {task.title}",
        )

        # Notify all admins
        admin_result = await db.execute(
            select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        )
        admins = admin_result.scalars().all()
        for admin in admins:
            notification = Notification(
                user_id=admin.id,
                title="Task Submitted",
                message=f"Task '{task.title}' has been submitted for review.",
            )
            db.add(notification)

        await db.flush()
        return task

    # ── Task Comments ─────────────────────────────────────────────────────────

    @staticmethod
    async def add_comment(
        db: AsyncSession,
        task_id: uuid.UUID,
        author_id: uuid.UUID,
        content: str,
    ) -> TaskComment:
        # Vérifier que la tâche existe
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        comment = TaskComment(
            task_id=task_id,
            author_id=author_id,
            content=content,
        )
        db.add(comment)
        await db.flush()
        await db.refresh(comment, ["author"])

        await ActivityLogService.log(
            db,
            user_id=author_id,
            action=ActivityAction.TASK_COMMENT,
            entity_id=task.id,
            entity_type="Task",
            detail=f"Comment on task: {task.title}",
        )

        # Notifier l'autre partie (admin → stagiaire ou stagiaire → admins)
        author_result = await db.execute(select(User).where(User.id == author_id))
        author = author_result.scalar_one_or_none()

        if author and author.role == UserRole.INTERN:
            # Notifier les admins
            admin_result = await db.execute(
                select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True))
            )
            for admin in admin_result.scalars().all():
                db.add(Notification(
                    user_id=admin.id,
                    title="Nouveau commentaire",
                    message=f"{author.full_name} a commenté la tâche '{task.title}'.",
                ))
        elif task.assigned_to:
            # Admin commente → notifier le stagiaire
            db.add(Notification(
                user_id=task.assigned_to,
                title="Nouveau commentaire",
                message=f"Un commentaire a été ajouté à votre tâche '{task.title}'.",
            ))

        await db.flush()
        return comment

    @staticmethod
    async def list_comments(
        db: AsyncSession, task_id: uuid.UUID, page: int = 1, size: int = 20
    ) -> tuple[list[TaskComment], int]:
        base = TaskComment.task_id == task_id
        total = (await db.execute(
            select(func.count()).select_from(TaskComment).where(base)
        )).scalar() or 0
        result = await db.execute(
            select(TaskComment)
            .options(selectinload(TaskComment.author))
            .where(base)
            .order_by(TaskComment.created_at.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def delete_comment(
        db: AsyncSession, comment_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        result = await db.execute(
            select(TaskComment).where(
                TaskComment.id == comment_id,
                TaskComment.author_id == user_id,
            )
        )
        comment = result.scalar_one_or_none()
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Commentaire introuvable ou vous n'êtes pas l'auteur",
            )
        await db.delete(comment)
        await db.flush()