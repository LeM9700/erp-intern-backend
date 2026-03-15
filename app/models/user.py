import enum
import uuid
from sqlalchemy import String, Boolean, Enum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, UUIDMixin, TimestampMixin


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    INTERN = "INTERN"


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False, default=UserRole.INTERN)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    attendance_sessions = relationship("AttendanceSession", back_populates="user", lazy="selectin")
    tasks_assigned = relationship("Task", back_populates="assigned_to_user", foreign_keys="Task.assigned_to", lazy="selectin")
    activity_logs = relationship("ActivityLog", back_populates="user", lazy="selectin")
    notifications = relationship("Notification", back_populates="user", lazy="selectin")
