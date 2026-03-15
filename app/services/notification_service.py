import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, status

from app.models.notification import Notification


class NotificationService:

    @staticmethod
    async def list_for_user(
        db: AsyncSession, user_id: uuid.UUID, page: int = 1, size: int = 20
    ) -> tuple[list[Notification], int]:
        base = Notification.user_id == user_id
        total = (await db.execute(
            select(func.count()).select_from(Notification).where(base)
        )).scalar() or 0
        result = await db.execute(
            select(Notification)
            .where(base)
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def mark_as_read(
        db: AsyncSession, notification_id: uuid.UUID, user_id: uuid.UUID
    ) -> Notification:
        result = await db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        notification = result.scalar_one_or_none()
        if not notification:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification introuvable")

        notification.is_read = True
        await db.flush()
        return notification

    @staticmethod
    async def mark_all_as_read(db: AsyncSession, user_id: uuid.UUID) -> int:
        result = await db.execute(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        )
        notifications = result.scalars().all()
        for n in notifications:
            n.is_read = True
        await db.flush()
        return len(notifications)
