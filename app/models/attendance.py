import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Text, Enum, ForeignKey, DateTime, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, UUIDMixin, TimestampMixin


class AttendanceStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class AttendanceSession(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "attendance_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus), nullable=False, default=AttendanceStatus.OPEN
    )
    clock_in_photo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id"), nullable=False
    )
    clock_out_photo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id"), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    user = relationship("User", back_populates="attendance_sessions")
    clock_in_photo = relationship("File", foreign_keys=[clock_in_photo_id])
    clock_out_photo = relationship("File", foreign_keys=[clock_out_photo_id])

    __table_args__ = (
        Index(
            "ix_unique_open_session_per_user",
            user_id,
            unique=True,
            postgresql_where=text("status = 'OPEN'"),
        ),
    )
