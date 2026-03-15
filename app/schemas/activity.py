from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

from app.models.activity import ActivityAction


class ActivityLogOut(BaseModel):
    id: UUID
    user_id: UUID
    action: ActivityAction
    detail: str | None
    entity_id: UUID | None
    entity_type: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ActivityLogListOut(BaseModel):
    items: list[ActivityLogOut]
    total: int
    page: int
    size: int
    pages: int
