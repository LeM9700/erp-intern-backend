import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.attendance import (
    AttendanceSessionOut,
    AttendanceSessionListOut,
    LiveAttendanceOut,
    AttendanceSummaryOut,
    AttendanceSessionSummaryItem,
    AdminAttendanceSessionOut,
    AdminAttendanceSessionListOut,
    ClockOutIn,
)
from app.services.attendance_service import AttendanceService, _ensure_utc
from app.schemas.pagination import paginate_meta
from app.utils.timezone import convert_to_tz, naive_to_utc

router = APIRouter(prefix="/attendance", tags=["Attendance"])


def _localize_session_out(s, tz_name: str) -> AttendanceSessionOut:
    """Construit un AttendanceSessionOut avec les timestamps convertis au fuseau tz_name."""
    return AttendanceSessionOut(
        id=s.id,
        user_id=s.user_id,
        clock_in_photo_id=s.clock_in_photo_id,
        clock_out_photo_id=s.clock_out_photo_id,
        status=s.status,
        note=s.note,
        created_at=convert_to_tz(s.created_at, tz_name),
        updated_at=convert_to_tz(s.updated_at, tz_name),
        ended_at=convert_to_tz(s.ended_at, tz_name),
    )


@router.post("/clock-in", response_model=AttendanceSessionOut, status_code=201)
async def clock_in(
    photo: UploadFile = File(..., description="Photo obligatoire pour le pointage"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        session = await AttendanceService.clock_in(db, current_user.id, photo)
        return _localize_session_out(session, current_user.timezone)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/clock-out", response_model=AttendanceSessionOut)
async def clock_out(
    body: ClockOutIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        session = await AttendanceService.clock_out(db, current_user.id, body.note)
        return _localize_session_out(session, current_user.timezone)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/current", response_model=AttendanceSessionOut | None)
async def get_current_session(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Renvoie la session ouverte de l'utilisateur courant, ou null."""
    session = await AttendanceService.get_current_open_session(db, current_user.id)
    if session is None:
        return None
    return _localize_session_out(session, current_user.timezone)


@router.get("/admin/live", response_model=list[LiveAttendanceOut])
async def get_live_sessions(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    sessions = await AttendanceService.get_live_sessions(db)
    return [
        LiveAttendanceOut(
            id=s.id,
            user_id=s.user_id,
            user_full_name=s.user.full_name,
            status=s.status,
            created_at=convert_to_tz(s.created_at, s.user.timezone),
            clock_in_photo_id=s.clock_in_photo_id,
        )
        for s in sessions
    ]


@router.get("/admin/summary/{user_id}", response_model=AttendanceSummaryOut)
async def get_user_summary(
    user_id: uuid.UUID,
    date_from: datetime | None = Query(None, alias="from", description="Début (ISO 8601)"),
    date_to: datetime | None = Query(None, alias="to", description="Fin (ISO 8601)"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    target_user = (await db.execute(
        sa_select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Stagiaire introuvable")
    return await _build_summary(db, target_user, date_from=date_from, date_to=date_to)


@router.get("/summary/me", response_model=AttendanceSummaryOut)
async def get_my_summary(
    date_from: datetime | None = Query(None, alias="from", description="Début (ISO 8601)"),
    date_to: datetime | None = Query(None, alias="to", description="Fin (ISO 8601)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _build_summary(db, current_user, date_from=date_from, date_to=date_to)


@router.get("/me", response_model=AttendanceSessionListOut)
async def get_my_sessions(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = await AttendanceService.get_user_sessions(db, current_user.id, page=page, size=size)
    return AttendanceSessionListOut(
        items=[_localize_session_out(s, current_user.timezone) for s in items],
        **paginate_meta(total, page, size).model_dump(),
    )


@router.get("/admin/sessions/{user_id}", response_model=AdminAttendanceSessionListOut)
async def get_intern_sessions(
    user_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    date_from: datetime | None = Query(None, alias="from", description="Début (ISO 8601)"),
    date_to: datetime | None = Query(None, alias="to", description="Fin (ISO 8601)"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Liste paginée de tous les pointages d'un stagiaire avec compte-rendus."""
    target_user = (await db.execute(
        sa_select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Stagiaire introuvable")

    tz_name = target_user.timezone
    date_from_utc = naive_to_utc(date_from, tz_name)
    date_to_utc = naive_to_utc(date_to, tz_name)

    sessions, total = await AttendanceService.get_user_sessions_admin(
        db, user_id, page=page, size=size, date_from=date_from_utc, date_to=date_to_utc
    )
    return AdminAttendanceSessionListOut(
        items=[_build_admin_session_out(s, tz_name) for s in sessions],
        **paginate_meta(total, page, size).model_dump(),
    )


@router.get("/admin/sessions/{user_id}/{session_id}", response_model=AdminAttendanceSessionOut)
async def get_intern_session_detail(
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Détail d'un pointage : heure d'entrée/sortie, durée, compte-rendu."""
    session = await AttendanceService.get_session_by_id(db, session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable")
    return _build_admin_session_out(session, session.user.timezone)


def _build_admin_session_out(s, tz_name: str) -> AdminAttendanceSessionOut:
    duration = None
    if s.ended_at:
        duration = round(
            (_ensure_utc(s.ended_at) - _ensure_utc(s.created_at)).total_seconds() / 60, 1
        )
    return AdminAttendanceSessionOut(
        id=s.id,
        user_id=s.user_id,
        user_full_name=s.user.full_name,
        status=s.status,
        clock_in=convert_to_tz(s.created_at, tz_name),
        clock_out=convert_to_tz(s.ended_at, tz_name),
        duration_minutes=duration,
        note=s.note,
        clock_in_photo_id=s.clock_in_photo_id,
        clock_out_photo_id=s.clock_out_photo_id,
    )


# ── Helper ────────────────────────────────────────────────────────────────────

async def _build_summary(
    db: AsyncSession,
    user: User,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> AttendanceSummaryOut:
    tz_name = user.timezone
    date_from_utc = naive_to_utc(date_from, tz_name)
    date_to_utc = naive_to_utc(date_to, tz_name)

    data = await AttendanceService.get_summary(db, user.id, date_from=date_from_utc, date_to=date_to_utc)
    items = [
        AttendanceSessionSummaryItem(
            id=s.id,
            clock_in=convert_to_tz(s.created_at, tz_name),
            clock_out=convert_to_tz(s.ended_at, tz_name),
            duration_minutes=round(
                (_ensure_utc(s.ended_at) - _ensure_utc(s.created_at)).total_seconds() / 60, 1
            ),
            note=s.note,
        )
        for s in data["sessions"]
    ]
    return AttendanceSummaryOut(
        user_id=data["user_id"],
        total_hours=data["total_hours"],
        total_sessions=data["total_sessions"],
        sessions=items,
    )
