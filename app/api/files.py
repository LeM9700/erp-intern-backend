import uuid
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.file_service import FileService

router = APIRouter(prefix="/files", tags=["Files"])

ALLOWED_UPLOAD_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


class PresignRequest(BaseModel):
    filename: str
    content_type: str


class ConfirmRequest(BaseModel):
    file_id: uuid.UUID


class FileOut(BaseModel):
    id: uuid.UUID
    original_filename: str
    stored_path: str
    mime_type: str
    size_bytes: int | None = None
    confirmed: bool

    model_config = {"from_attributes": True}


@router.post("/upload", response_model=FileOut, status_code=201)
async def upload_file_direct(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a file directly (multipart/form-data)."""
    # content_type is client-reported and cannot be fully trusted.
    # For stronger validation, inspect magic bytes with python-magic.
    # This check is sufficient for an internal tool with known users.
    if file.content_type not in ALLOWED_UPLOAD_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Type MIME non autorisé : {file.content_type}. Types acceptés : image/jpeg, image/png, image/webp",
        )
    try:
        db_file = await FileService.upload_photo(db, file, current_user.id)
        return db_file
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/presign")
async def presign(
    body: PresignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.content_type not in ALLOWED_UPLOAD_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Type MIME non autorisé : {body.content_type}",
        )
    try:
        return await FileService.presign(db, current_user.id, body.filename, body.content_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/confirm")
async def confirm(
    body: ConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        f = await FileService.confirm(db, body.file_id, current_user.id)
        return {"file_id": str(f.id), "confirmed": f.confirmed}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
