"""Integration tests for /api/v1/files endpoints."""
import uuid
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.file import File

FAKE_PHOTO = ("photo.jpg", b"fake-image-content", "image/jpeg")


class TestDirectUpload:
    @pytest.mark.asyncio
    async def test_upload_success(self, client: AsyncClient, intern_headers: dict):
        with patch("app.services.storage.StorageService.save_upload_locally", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = {
                "original_filename": "photo.jpg",
                "stored_path": "uploads/photos/test/photo.jpg",
                "mime_type": "image/jpeg",
                "size_bytes": 18,
            }
            resp = await client.post(
                "/api/v1/files/upload",
                files={"file": FAKE_PHOTO},
                headers=intern_headers,
            )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["confirmed"] is True

    @pytest.mark.asyncio
    async def test_upload_invalid_content_type(self, client: AsyncClient, intern_headers: dict):
        resp = await client.post(
            "/api/v1/files/upload",
            files={"file": ("doc.txt", b"text", "text/plain")},
            headers=intern_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_unauthenticated(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/files/upload",
            files={"file": FAKE_PHOTO},
        )
        assert resp.status_code == 401


class TestPresign:
    @pytest.mark.asyncio
    async def test_presign_success(self, client: AsyncClient, intern_headers: dict):
        with patch("app.services.storage.StorageService.generate_presigned_url", new_callable=AsyncMock) as mock_presign:
            mock_presign.return_value = {
                "upload_url": "https://s3.example.com/upload?token=abc",
                "key": "uploads/abc123/photo.jpg",
            }
            resp = await client.post(
                "/api/v1/files/presign",
                json={"filename": "photo.jpg", "content_type": "image/jpeg"},
                headers=intern_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "file_id" in data
        assert data["upload_url"] == "https://s3.example.com/upload?token=abc"

    @pytest.mark.asyncio
    async def test_presign_unauthenticated(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/files/presign",
            json={"filename": "photo.jpg", "content_type": "image/jpeg"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_presign_missing_fields(self, client: AsyncClient, intern_headers: dict):
        resp = await client.post(
            "/api/v1/files/presign",
            json={},
            headers=intern_headers,
        )
        assert resp.status_code == 422


class TestConfirm:
    @pytest.mark.asyncio
    async def test_confirm_success(
        self, client: AsyncClient, intern_headers: dict, db_session: AsyncSession, intern_user: User
    ):
        pending_file = File(
            id=uuid.uuid4(),
            original_filename="report.pdf",
            stored_path=f"uploads/{intern_user.id}/{uuid.uuid4()}/report.pdf",
            mime_type="application/pdf",
            confirmed=False,
            uploaded_by=intern_user.id,
        )
        db_session.add(pending_file)
        await db_session.commit()

        with patch("app.services.storage.StorageService.confirm_upload", new_callable=AsyncMock) as mock_confirm:
            mock_confirm.return_value = True
            resp = await client.post(
                "/api/v1/files/confirm",
                json={"file_id": str(pending_file.id)},
                headers=intern_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["confirmed"] is True
        assert data["file_id"] == str(pending_file.id)

    @pytest.mark.asyncio
    async def test_confirm_file_not_found(self, client: AsyncClient, intern_headers: dict):
        resp = await client.post(
            "/api/v1/files/confirm",
            json={"file_id": str(uuid.uuid4())},
            headers=intern_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_confirm_not_uploaded_to_storage(
        self, client: AsyncClient, intern_headers: dict, db_session: AsyncSession, intern_user: User
    ):
        pending_file = File(
            id=uuid.uuid4(),
            original_filename="missing.pdf",
            stored_path=f"uploads/{intern_user.id}/{uuid.uuid4()}/missing.pdf",
            mime_type="application/pdf",
            confirmed=False,
            uploaded_by=intern_user.id,
        )
        db_session.add(pending_file)
        await db_session.commit()

        with patch("app.services.storage.StorageService.confirm_upload", new_callable=AsyncMock) as mock_confirm:
            mock_confirm.return_value = False
            resp = await client.post(
                "/api/v1/files/confirm",
                json={"file_id": str(pending_file.id)},
                headers=intern_headers,
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_confirm_already_confirmed(
        self, client: AsyncClient, intern_headers: dict, confirmed_file: File
    ):
        resp = await client.post(
            "/api/v1/files/confirm",
            json={"file_id": str(confirmed_file.id)},
            headers=intern_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["confirmed"] is True

    @pytest.mark.asyncio
    async def test_confirm_unauthenticated(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/files/confirm",
            json={"file_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 401
