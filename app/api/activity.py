from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.session import get_db
from app.core.dependencies import get_current_user, require_admin
from app.models.user import User
from app.models.activity import ActivityLog
from app.schemas.activity import ActivityLogOut, ActivityLogListOut
from app.schemas.pagination import paginate_meta

router = APIRouter(prefix="/activity", tags=["Activity"])


@router.get("", response_model=ActivityLogListOut)
async def list_all_activity(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count()).select_from(ActivityLog))).scalar() or 0
    result = await db.execute(
        select(ActivityLog)
        .order_by(ActivityLog.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return ActivityLogListOut(
        items=list(result.scalars().all()),
        **paginate_meta(total, page, size).model_dump(),
    )


@router.get("/me", response_model=ActivityLogListOut)
async def list_my_activity(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    base = select(ActivityLog).where(ActivityLog.user_id == current_user.id)
    total = (await db.execute(
        select(func.count()).select_from(ActivityLog).where(ActivityLog.user_id == current_user.id)
    )).scalar() or 0
    result = await db.execute(
        base.order_by(ActivityLog.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return ActivityLogListOut(
        items=list(result.scalars().all()),
        **paginate_meta(total, page, size).model_dump(),
    )
