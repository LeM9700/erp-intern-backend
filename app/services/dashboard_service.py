"""Service pour le dashboard admin avec KPIs."""
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models.user import User, UserRole
from app.models.attendance import AttendanceSession, AttendanceStatus
from app.models.task import Task, TaskStatus
from app.schemas.dashboard import DashboardKPIs, InternSummary


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class DashboardService:

    @staticmethod
    async def get_kpis(db: AsyncSession) -> DashboardKPIs:
        now = datetime.now(timezone.utc)

        # Calcul des bornes semaine (lundi 00:00) et mois (1er 00:00)
        weekday = now.weekday()  # 0=lundi
        week_start = (now - timedelta(days=weekday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # ── Interns ──
        intern_result = await db.execute(
            select(User).where(User.role == UserRole.INTERN)
        )
        interns = intern_result.scalars().all()
        total_interns = len(interns)
        active_interns = sum(1 for i in interns if i.is_active)

        # ── Sessions live ──
        live_result = await db.execute(
            select(func.count()).select_from(AttendanceSession).where(
                AttendanceSession.status == AttendanceStatus.OPEN,
            )
        )
        live_sessions_count = live_result.scalar() or 0

        # ── Tâches globales ──
        task_counts = {}
        for status_val in TaskStatus:
            count_result = await db.execute(
                select(func.count()).select_from(Task).where(Task.status == status_val)
            )
            task_counts[status_val] = count_result.scalar() or 0

        # ── Par stagiaire ──
        intern_summaries = []
        total_hours_week = 0.0
        total_hours_month = 0.0

        for intern in interns:
            # Sessions fermées ce mois
            sessions_result = await db.execute(
                select(AttendanceSession).where(
                    AttendanceSession.user_id == intern.id,
                    AttendanceSession.status == AttendanceStatus.CLOSED,
                    AttendanceSession.ended_at.isnot(None),
                    AttendanceSession.created_at >= month_start,
                )
            )
            sessions = sessions_result.scalars().all()

            hours_week = 0.0
            hours_month = 0.0
            for s in sessions:
                duration = (
                    _ensure_utc(s.ended_at) - _ensure_utc(s.created_at)
                ).total_seconds() / 3600
                hours_month += duration
                if _ensure_utc(s.created_at) >= week_start:
                    hours_week += duration

            total_hours_week += hours_week
            total_hours_month += hours_month

            # Session en cours ?
            open_result = await db.execute(
                select(func.count()).select_from(AttendanceSession).where(
                    AttendanceSession.user_id == intern.id,
                    AttendanceSession.status == AttendanceStatus.OPEN,
                )
            )
            is_clocked_in = (open_result.scalar() or 0) > 0

            # Tâches par statut pour ce stagiaire
            intern_task_counts = {}
            for status_val in TaskStatus:
                tc_result = await db.execute(
                    select(func.count()).select_from(Task).where(
                        Task.assigned_to == intern.id,
                        Task.status == status_val,
                    )
                )
                intern_task_counts[status_val] = tc_result.scalar() or 0

            intern_summaries.append(InternSummary(
                user_id=intern.id,
                full_name=intern.full_name,
                email=intern.email,
                hours_this_week=round(hours_week, 2),
                hours_this_month=round(hours_month, 2),
                is_currently_clocked_in=is_clocked_in,
                tasks_pending=intern_task_counts[TaskStatus.PENDING],
                tasks_in_progress=intern_task_counts[TaskStatus.IN_PROGRESS],
                tasks_submitted=intern_task_counts[TaskStatus.SUBMITTED],
                tasks_approved=intern_task_counts[TaskStatus.APPROVED],
                tasks_rejected=intern_task_counts[TaskStatus.REJECTED],
            ))

        return DashboardKPIs(
            total_interns=total_interns,
            active_interns=active_interns,
            live_sessions_count=live_sessions_count,
            total_hours_this_week=round(total_hours_week, 2),
            total_hours_this_month=round(total_hours_month, 2),
            tasks_pending=task_counts[TaskStatus.PENDING],
            tasks_in_progress=task_counts[TaskStatus.IN_PROGRESS],
            tasks_submitted=task_counts[TaskStatus.SUBMITTED],
            tasks_approved=task_counts[TaskStatus.APPROVED],
            tasks_rejected=task_counts[TaskStatus.REJECTED],
            interns=intern_summaries,
        )
