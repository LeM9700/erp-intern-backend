from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

from app.models.file import FileStatus


# ── Input ──
class PresignRequest(BaseModel):
    filename: str
    content_type: str


class ConfirmUploadRequest(BaseModel):
    file_id: UUID


# ── Output ──
class PresignResponse(BaseModel):
    file_id: UUID
    upload_url: str
    s3_key: str


class FileOut(BaseModel):
    id: UUID
    original_name: str
    s3_key: str
    content_type: str
    size_bytes: int | None
    status: FileStatus
    uploaded_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
