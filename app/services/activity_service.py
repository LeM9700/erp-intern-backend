import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityLog, ActivityAction


class ActivityLogService:

    @staticmethod
    async def log(
        db: AsyncSession,
        user_id: uuid.UUID,
        action: ActivityAction,
        entity_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        detail: str | None = None,
    ) -> ActivityLog:
        entry = ActivityLog(
            user_id=user_id,
            action=action,
            entity_id=entity_id,
            entity_type=entity_type,
            detail=detail,
        )
        db.add(entry)
        await db.flush()
        return entry
