import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
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

router = APIRouter(prefix="/attendance", tags=["Attendance"])


@router.post("/clock-in", response_model=AttendanceSessionOut, status_code=201)
async def clock_in(
    photo: UploadFile = File(..., description="Photo obligatoire pour le pointage"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await AttendanceService.clock_in(db, current_user.id, photo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/clock-out", response_model=AttendanceSessionOut)
async def clock_out(
    body: ClockOutIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await AttendanceService.clock_out(db, current_user.id, body.note)
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
    return session


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
            created_at=s.created_at,
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
    return await _build_summary(db, user_id, date_from=date_from, date_to=date_to)


@router.get("/summary/me", response_model=AttendanceSummaryOut)
async def get_my_summary(
    date_from: datetime | None = Query(None, alias="from", description="Début (ISO 8601)"),
    date_to: datetime | None = Query(None, alias="to", description="Fin (ISO 8601)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _build_summary(db, current_user.id, date_from=date_from, date_to=date_to)


@router.get("/me", response_model=AttendanceSessionListOut)
async def get_my_sessions(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = await AttendanceService.get_user_sessions(db, current_user.id, page=page, size=size)
    return AttendanceSessionListOut(
        items=items,
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
    from sqlalchemy import select as sa_select
    from app.models.user import User as UserModel
    user_exists = (await db.execute(
        sa_select(UserModel.id).where(UserModel.id == user_id)
    )).scalar_one_or_none()
    if not user_exists:
        raise HTTPException(status_code=404, detail="Stagiaire introuvable")

    sessions, total = await AttendanceService.get_user_sessions_admin(
        db, user_id, page=page, size=size, date_from=date_from, date_to=date_to
    )
    return AdminAttendanceSessionListOut(
        items=[_build_admin_session_out(s) for s in sessions],
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
    return _build_admin_session_out(session)


def _build_admin_session_out(s) -> AdminAttendanceSessionOut:
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
        clock_in=s.created_at,
        clock_out=s.ended_at,
        duration_minutes=duration,
        note=s.note,
        clock_in_photo_id=s.clock_in_photo_id,
        clock_out_photo_id=s.clock_out_photo_id,
    )


# ── Helper ────────────────────────────────────────────────────────────────────

async def _build_summary(
    db: AsyncSession,
    user_id: uuid.UUID,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> AttendanceSummaryOut:
    data = await AttendanceService.get_summary(db, user_id, date_from=date_from, date_to=date_to)
    items = [
        AttendanceSessionSummaryItem(
            id=s.id,
            clock_in=s.created_at,
            clock_out=s.ended_at,
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
