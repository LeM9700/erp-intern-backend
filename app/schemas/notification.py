from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class NotificationOut(BaseModel):
    id: UUID
    title: str
    message: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int
    page: int
    size: int
    pages: int
