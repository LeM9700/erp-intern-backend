import uuid
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.file import File
from app.models.activity import ActivityAction
from app.services.storage import StorageService
from app.services.activity_service import ActivityLogService

settings = get_settings()


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class FileService:

    @staticmethod
    async def upload_photo(
        db: AsyncSession,
        file: UploadFile,
        user_id: uuid.UUID,
        subfolder: str = "photos",
    ) -> File:
        """Upload a photo directly and create a confirmed File record."""
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise ValueError(f"Invalid file type: {file.content_type}. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}")

        if settings.USE_S3:
            meta = await StorageService.upload_to_s3(file, user_id, subfolder)
            if meta["size_bytes"] > MAX_FILE_SIZE:
                raise ValueError(f"File too large ({meta['size_bytes']} bytes). Max: {MAX_FILE_SIZE} bytes.")
        else:
            meta = await StorageService.save_upload_locally(file, user_id, subfolder)
            if meta["size_bytes"] > MAX_FILE_SIZE:
                StorageService.delete_local_file(meta["stored_path"])
                raise ValueError(f"File too large ({meta['size_bytes']} bytes). Max: {MAX_FILE_SIZE} bytes.")

        db_file = File(
            original_filename=meta["original_filename"],
            stored_path=meta["stored_path"],
            mime_type=meta["mime_type"],
            size_bytes=meta["size_bytes"],
            uploaded_by=user_id,
            confirmed=True,
        )
        db.add(db_file)
        await db.flush()

        await ActivityLogService.log(
            db,
            user_id=user_id,
            action=ActivityAction.FILE_UPLOAD,
            entity_id=db_file.id,
            entity_type="File",
            detail=f"Uploaded: {db_file.original_filename}",
        )

        return db_file

    @staticmethod
    async def get_file(db: AsyncSession, file_id: uuid.UUID) -> File | None:
        result = await db.execute(select(File).where(File.id == file_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def presign(db: AsyncSession, user_id: uuid.UUID, filename: str, content_type: str) -> dict:
        data = await StorageService.generate_presigned_url(filename, content_type)
        db_file = File(
            original_filename=filename,
            stored_path=data["key"],
            mime_type=content_type,
            uploaded_by=user_id,
            confirmed=False,
        )
        db.add(db_file)
        await db.flush()
        return {"upload_url": data["upload_url"], "file_id": str(db_file.id)}

    @staticmethod
    async def confirm(db: AsyncSession, file_id: uuid.UUID, user_id: uuid.UUID) -> File:
        result = await db.execute(
            select(File).where(File.id == file_id, File.uploaded_by == user_id)
        )
        db_file = result.scalar_one_or_none()
        if not db_file:
            raise ValueError("File not found")
        if db_file.confirmed:
            return db_file
        exists = await StorageService.confirm_upload(db_file.stored_path)
        if not exists:
            raise ValueError("File not found on storage")
        db_file.confirmed = True
        await db.flush()
        await ActivityLogService.log(
            db,
            user_id=user_id,
            action=ActivityAction.FILE_UPLOAD,
            entity_id=db_file.id,
            entity_type="File",
            detail=f"Confirmed: {db_file.original_filename}",
        )
        return db_file
