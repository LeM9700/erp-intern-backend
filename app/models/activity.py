import enum
import uuid
from sqlalchemy import String, Text, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, UUIDMixin, TimestampMixin


class ActivityAction(str, enum.Enum):
    CLOCK_IN = "CLOCK_IN"
    CLOCK_OUT = "CLOCK_OUT"
    TASK_START = "TASK_START"
    TASK_SUBMIT = "TASK_SUBMIT"
    TASK_ASSIGN = "TASK_ASSIGN"
    TASK_APPROVE = "TASK_APPROVE"
    TASK_REJECT = "TASK_REJECT"
    TASK_COMMENT = "TASK_COMMENT"
    FILE_UPLOAD = "FILE_UPLOAD"


class ActivityLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "activity_logs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    action: Mapped[ActivityAction] = mapped_column(Enum(ActivityAction), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    user = relationship("User", back_populates="activity_logs")
