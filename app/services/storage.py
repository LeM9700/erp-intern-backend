import os
import uuid
import shutil
from pathlib import Path
from datetime import datetime

import aioboto3
from fastapi import UploadFile

from app.core.config import get_settings

settings = get_settings()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


class StorageService:
    """Abstraction over S3-compatible and local file storage."""

    @staticmethod
    async def save_upload_locally(file: UploadFile, user_id: uuid.UUID, subfolder: str = "photos") -> dict:
        """Save an uploaded file to local disk. Returns file metadata."""
        ext = Path(file.filename or "photo.jpg").suffix or ".jpg"
        unique_name = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
        dest_dir = UPLOAD_DIR / subfolder / str(user_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / unique_name

        content = await file.read()
        with open(dest_path, "wb") as f:
            f.write(content)

        return {
            "original_filename": file.filename or "photo.jpg",
            "stored_path": str(dest_path),
            "mime_type": file.content_type or "image/jpeg",
            "size_bytes": len(content),
        }

    @staticmethod
    async def generate_presigned_url(filename: str, content_type: str) -> dict:
        key = f"uploads/{uuid.uuid4().hex}/{filename}"
        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
        ) as client:
            url = await client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.S3_BUCKET_NAME,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=settings.S3_PRESIGN_EXPIRATION,
            )
        return {"upload_url": url, "key": key}

    @staticmethod
    async def confirm_upload(key: str) -> bool:
        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
        ) as client:
            try:
                await client.head_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
                return True
            except Exception:
                return False

    @staticmethod
    async def upload_to_s3(file: UploadFile, user_id: uuid.UUID, subfolder: str = "photos") -> dict:
        """Upload a file directly to S3-compatible storage. Returns file metadata."""
        ext = Path(file.filename or "photo.jpg").suffix or ".jpg"
        unique_name = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
        key = f"{subfolder}/{user_id}/{unique_name}"

        content = await file.read()

        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
        ) as client:
            await client.put_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=key,
                Body=content,
                ContentType=file.content_type or "image/jpeg",
            )

        return {
            "original_filename": file.filename or "photo.jpg",
            "stored_path": key,
            "mime_type": file.content_type or "image/jpeg",
            "size_bytes": len(content),
        }

    @staticmethod
    async def generate_presigned_download_url(key: str) -> str:
        """Generate a presigned GET URL for a stored S3 object."""
        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
        ) as client:
            url = await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.S3_BUCKET_NAME, "Key": key},
                ExpiresIn=settings.S3_PRESIGN_EXPIRATION,
            )
        return url

    @staticmethod
    def delete_local_file(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass