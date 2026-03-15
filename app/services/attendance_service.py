import uuid
from datetime import datetime, timezone, timedelta

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from fastapi import HTTPException, status

def _ensure_utc(dt: datetime) -> datetime:
    """Garantit qu'un datetime est timezone-aware UTC (compatibilité SQLite)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


from app.models.attendance import AttendanceSession, AttendanceStatus
from app.models.notification import Notification
from app.models.user import User, UserRole
from app.models.activity import ActivityAction
from app.services.activity_service import ActivityLogService
from app.services.file_service import FileService

MAX_SESSION_DURATION = timedelta(hours=4, minutes=30)   # Règle 1
MIN_PAUSE_BEFORE_RECLOCKING = timedelta(minutes=30)     # Règle 2
MIN_DURATION_BEFORE_CLOCKOUT = timedelta(minutes=30)    # Règle 3
NOTE_MIN_CHARS = 200                                    # Règle 4
DAILY_MAX_WORK = timedelta(hours=5)                     # Règle 6
MANDATORY_REST = timedelta(hours=12)                    # Règle 6


class AttendanceService:

    # ── Helpers règles métier ─────────────────────────────────────────────────

    @staticmethod
    async def _check_pause_rule(db: AsyncSession, user_id: uuid.UUID):
        """Règle 2 : pause de 30 min minimum avant de se repointer."""
        result = await db.execute(
            select(AttendanceSession)
            .where(
                AttendanceSession.user_id == user_id,
                AttendanceSession.status == AttendanceStatus.CLOSED,
                AttendanceSession.ended_at.isnot(None),
            )
            .order_by(AttendanceSession.ended_at.desc())
            .limit(1)
        )
        last = result.scalar_one_or_none()
        if not last:
            return
        elapsed = datetime.now(timezone.utc) - _ensure_utc(last.ended_at)
        if elapsed < MIN_PAUSE_BEFORE_RECLOCKING:
            remaining = MIN_PAUSE_BEFORE_RECLOCKING - elapsed
            mins = int(remaining.total_seconds() // 60) + 1
            raise ValueError(
                f"Pause obligatoire de 30 min entre deux pointages. "
                f"Vous pouvez vous repointer dans {mins} min."
            )

    @staticmethod
    async def _check_daily_rest_rule(db: AsyncSession, user_id: uuid.UUID):
        """Règle 6 : 12h de repos consécutif après 5h cumulées dans une journée de travail."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=48)

        result = await db.execute(
            select(AttendanceSession)
            .where(
                AttendanceSession.user_id == user_id,
                AttendanceSession.status == AttendanceStatus.CLOSED,
                AttendanceSession.ended_at.isnot(None),
                AttendanceSession.created_at >= cutoff,
            )
            .order_by(AttendanceSession.created_at.asc())
        )
        sessions = result.scalars().all()
        if not sessions:
            return

        # Regrouper en périodes de travail (gap >= 12h = nouvelle période)
        periods: list[list[AttendanceSession]] = []
        current: list[AttendanceSession] = [sessions[0]]
        for s in sessions[1:]:
            gap = _ensure_utc(s.created_at) - _ensure_utc(current[-1].ended_at)
            if gap < MANDATORY_REST:
                current.append(s)
            else:
                periods.append(current)
                current = [s]
        periods.append(current)

        # Vérifier la période la plus récente
        last_period = periods[-1]
        total_seconds = sum(
            (_ensure_utc(s.ended_at) - _ensure_utc(s.created_at)).total_seconds()
            for s in last_period
            if s.ended_at
        )

        if total_seconds >= DAILY_MAX_WORK.total_seconds():
            last_out = _ensure_utc(last_period[-1].ended_at)
            time_since = now - last_out
            if time_since < MANDATORY_REST:
                remaining = MANDATORY_REST - time_since
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                raise ValueError(
                    f"Repos obligatoire de 12h après une journée de 5h cumulées. "
                    f"Vous pouvez vous repointer dans {hours}h{minutes:02d}min."
                )

    # ── Current open session ────────────────────────────────────────────────

    @staticmethod
    async def get_current_open_session(
        db: AsyncSession, user_id: uuid.UUID
    ) -> AttendanceSession | None:
        """Renvoie la session OPEN de l'utilisateur, ou None."""
        result = await db.execute(
            select(AttendanceSession).where(
                AttendanceSession.user_id == user_id,
                AttendanceSession.status == AttendanceStatus.OPEN,
            )
        )
        return result.scalar_one_or_none()

    # ── Clock-in ──────────────────────────────────────────────────────────────

    @staticmethod
    async def clock_in(
        db: AsyncSession, user_id: uuid.UUID, photo: UploadFile
    ) -> AttendanceSession:
        # Vérifier session déjà ouverte
        existing = await db.execute(
            select(AttendanceSession).where(
                AttendanceSession.user_id == user_id,
                AttendanceSession.status == AttendanceStatus.OPEN,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Une session de pointage est déjà ouverte")

        # Règle 2 : pause 30 min
        await AttendanceService._check_pause_rule(db, user_id)

        # Règle 6 : repos 12h après 5h cumulées
        await AttendanceService._check_daily_rest_rule(db, user_id)

        file_record = await FileService.upload_photo(db, photo, user_id, subfolder="attendance")

        session = AttendanceSession(
            user_id=user_id,
            clock_in_photo_id=file_record.id,
            status=AttendanceStatus.OPEN,
        )
        db.add(session)
        await db.flush()

        await ActivityLogService.log(
            db,
            user_id=user_id,
            action=ActivityAction.CLOCK_IN,
            entity_id=session.id,
            entity_type="AttendanceSession",
            detail="Pointage entrant",
        )

        return session

    # ── Clock-out ─────────────────────────────────────────────────────────────

    @staticmethod
    async def clock_out(
        db: AsyncSession, user_id: uuid.UUID, note: str
    ) -> AttendanceSession:
        # Règle 4 : compte-rendu 200 caractères minimum
        if len(note.strip()) < NOTE_MIN_CHARS:
            raise ValueError(
                f"Le compte-rendu doit contenir au moins {NOTE_MIN_CHARS} caractères "
                f"(actuellement : {len(note.strip())})."
            )

        result = await db.execute(
            select(AttendanceSession).where(
                AttendanceSession.user_id == user_id,
                AttendanceSession.status == AttendanceStatus.OPEN,
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aucune session de pointage ouverte")

        # Règle 3 : rester pointé au moins 30 min
        elapsed = datetime.now(timezone.utc) - _ensure_utc(session.created_at)
        if elapsed < MIN_DURATION_BEFORE_CLOCKOUT:
            remaining = MIN_DURATION_BEFORE_CLOCKOUT - elapsed
            mins = int(remaining.total_seconds() // 60) + 1
            raise ValueError(
                f"Vous devez rester pointé au moins 30 min avant de dépointer. "
                f"Dépointage possible dans {mins} min."
            )

        session.ended_at = datetime.now(timezone.utc)
        session.status = AttendanceStatus.CLOSED
        session.note = note.strip()
        await db.flush()

        await ActivityLogService.log(
            db,
            user_id=user_id,
            action=ActivityAction.CLOCK_OUT,
            entity_id=session.id,
            entity_type="AttendanceSession",
            detail="Pointage sortant",
        )

        return session

    # ── Auto-fermeture (règle 1) ──────────────────────────────────────────────

    @staticmethod
    async def auto_close_expired_sessions(db: AsyncSession) -> None:
        """Ferme automatiquement les sessions ouvertes depuis plus de 4h30."""
        limit = datetime.now(timezone.utc) - MAX_SESSION_DURATION
        result = await db.execute(
            select(AttendanceSession)
            .options(selectinload(AttendanceSession.user))
            .where(
                AttendanceSession.status == AttendanceStatus.OPEN,
                AttendanceSession.created_at <= limit,
            )
        )
        sessions = result.scalars().all()
        if not sessions:
            return

        for session in sessions:
            session.status = AttendanceStatus.CLOSED
            session.ended_at = datetime.now(timezone.utc)
            session.note = "Session fermée automatiquement après 4h30 de pointage."

        # Notifier tous les admins
        admin_result = await db.execute(
            select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        )
        admins = admin_result.scalars().all()
        for session in sessions:
            for admin in admins:
                db.add(Notification(
                    user_id=admin.id,
                    title="Session auto-fermée",
                    message=(
                        f"La session de {session.user.full_name} a été fermée automatiquement "
                        f"après 4h30 de pointage (entrée : {session.created_at.strftime('%H:%M')})."
                    ),
                ))

        await db.flush()

    # ── Résumé (règle 5) ──────────────────────────────────────────────────────

    @staticmethod
    async def get_summary(
        db: AsyncSession,
        user_id: uuid.UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict:
        conditions = [
            AttendanceSession.user_id == user_id,
            AttendanceSession.status == AttendanceStatus.CLOSED,
            AttendanceSession.ended_at.isnot(None),
        ]
        if date_from:
            conditions.append(AttendanceSession.created_at >= date_from)
        if date_to:
            conditions.append(AttendanceSession.created_at <= date_to)

        result = await db.execute(
            select(AttendanceSession)
            .where(*conditions)
            .order_by(AttendanceSession.created_at.desc())
        )
        sessions = result.scalars().all()

        total_seconds = sum(
            (_ensure_utc(s.ended_at) - _ensure_utc(s.created_at)).total_seconds()
            for s in sessions
        )
        total_hours = total_seconds / 3600

        return {
            "user_id": user_id,
            "total_hours": round(total_hours, 2),
            "total_sessions": len(sessions),
            "sessions": sessions,
        }

    # ── Autres ───────────────────────────────────────────────────────────────

    @staticmethod
    async def get_live_sessions(db: AsyncSession) -> list[AttendanceSession]:
        result = await db.execute(
            select(AttendanceSession)
            .options(selectinload(AttendanceSession.user))
            .where(AttendanceSession.status == AttendanceStatus.OPEN)
            .order_by(AttendanceSession.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_user_sessions(
        db: AsyncSession, user_id: uuid.UUID, page: int = 1, size: int = 20
    ) -> tuple[list[AttendanceSession], int]:
        from sqlalchemy import func as sa_func

        base = AttendanceSession.user_id == user_id
        total = (await db.execute(
            select(sa_func.count()).select_from(AttendanceSession).where(base)
        )).scalar() or 0
        result = await db.execute(
            select(AttendanceSession)
            .where(base)
            .order_by(AttendanceSession.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(result.scalars().all()), total
