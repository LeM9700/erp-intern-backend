import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Text, Enum, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, UUIDMixin, TimestampMixin


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class TaskPriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Task(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority), nullable=False, default=TaskPriority.MEDIUM
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assigned_to_user = relationship("User", back_populates="tasks_assigned", foreign_keys=[assigned_to])
    created_by_user = relationship("User", foreign_keys=[created_by])
    proofs = relationship("TaskProof", back_populates="task", lazy="selectin")
    reviews = relationship("TaskReview", back_populates="task", lazy="selectin")
    comments = relationship("TaskComment", back_populates="task", lazy="selectin")


class TaskProof(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "task_proofs"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False, index=True
    )
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id"), nullable=True, index=True
    )
    proof_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)

    task = relationship("Task", back_populates="proofs")
    file = relationship("File")


class TaskReview(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "task_reviews"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False, index=True
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    task = relationship("Task", back_populates="reviews")
    reviewer = relationship("User")


class TaskComment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "task_comments"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    task = relationship("Task", back_populates="comments")
    author = relationship("User")

    @property
    def author_full_name(self) -> str:
        return self.author.full_name if self.author else ""
