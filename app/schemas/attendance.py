from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

from app.models.attendance import AttendanceStatus


# ── Input ──
class ClockOutIn(BaseModel):
    note: str


# ── Output ──
class AttendanceSessionOut(BaseModel):
    id: UUID
    user_id: UUID
    clock_in_photo_id: UUID
    clock_out_photo_id: UUID | None = None
    status: AttendanceStatus
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None = None

    model_config = {"from_attributes": True}


class AttendanceSessionListOut(BaseModel):
    items: list[AttendanceSessionOut]
    total: int
    page: int
    size: int
    pages: int


class LiveAttendanceOut(BaseModel):
    id: UUID
    user_id: UUID
    user_full_name: str
    status: AttendanceStatus
    created_at: datetime
    clock_in_photo_id: UUID | None = None

    model_config = {"from_attributes": True}


class AttendanceSessionSummaryItem(BaseModel):
    id: UUID
    clock_in: datetime
    clock_out: datetime
    duration_minutes: float
    note: str | None = None

    model_config = {"from_attributes": True}


class AttendanceSummaryOut(BaseModel):
    user_id: UUID
    total_hours: float
    total_sessions: int
    sessions: list[AttendanceSessionSummaryItem]


# ── Admin ──
class AdminAttendanceSessionOut(BaseModel):
    id: UUID
    user_id: UUID
    user_full_name: str
    status: AttendanceStatus
    clock_in: datetime
    clock_out: Optional[datetime] = None
    duration_minutes: Optional[float] = None
    note: Optional[str] = None
    clock_in_photo_id: UUID
    clock_out_photo_id: Optional[UUID] = None

    model_config = {"from_attributes": True}


class AdminAttendanceSessionListOut(BaseModel):
    items: list[AdminAttendanceSessionOut]
    total: int
    page: int
    size: int
    pages: int
