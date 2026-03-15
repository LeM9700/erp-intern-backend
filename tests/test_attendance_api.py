"""Integration tests for /api/v1/attendance endpoints."""
import uuid
from datetime import timedelta
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceSession, AttendanceStatus
from app.models.user import User

FAKE_PHOTO = ("photo.jpg", b"fake-image-content", "image/jpeg")
FAKE_PHOTO2 = ("photo2.jpg", b"fake-image-content-2", "image/jpeg")
VALID_NOTE = "A" * 200  # 200 caractères = note valide

MOCK_SAVE = {
    "original_filename": "photo.jpg",
    "stored_path": "uploads/attendance/test/photo.jpg",
    "mime_type": "image/jpeg",
    "size_bytes": 18,
}


def mock_storage():
    return patch(
        "app.services.storage.StorageService.save_upload_locally",
        new_callable=AsyncMock,
        return_value=MOCK_SAVE,
    )


def bypass_min_duration():
    """Contourne la règle 3 (30 min minimum) pour les tests."""
    return patch("app.services.attendance_service.MIN_DURATION_BEFORE_CLOCKOUT", timedelta(0))


def bypass_pause_rule():
    """Contourne la règle 2 (30 min de pause) pour les tests."""
    return patch("app.services.attendance_service.MIN_PAUSE_BEFORE_RECLOCKING", timedelta(0))


class TestClockIn:

    async def test_clock_in_success(self, client: AsyncClient, intern_headers: dict):
        with mock_storage():
            resp = await client.post(
                "/api/v1/attendance/clock-in",
                files={"photo": FAKE_PHOTO},
                headers=intern_headers,
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "OPEN"
        assert "clock_in_photo_id" in data

    async def test_clock_in_unauthenticated(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/attendance/clock-in",
            files={"photo": FAKE_PHOTO},
        )
        assert resp.status_code == 401

    async def test_clock_in_invalid_content_type(self, client: AsyncClient, intern_headers: dict):
        resp = await client.post(
            "/api/v1/attendance/clock-in",
            files={"photo": ("doc.txt", b"text content", "text/plain")},
            headers=intern_headers,
        )
        assert resp.status_code == 400

    async def test_clock_in_duplicate_session(self, client: AsyncClient, intern_headers: dict):
        with mock_storage():
            await client.post(
                "/api/v1/attendance/clock-in",
                files={"photo": FAKE_PHOTO},
                headers=intern_headers,
            )
            resp = await client.post(
                "/api/v1/attendance/clock-in",
                files={"photo": FAKE_PHOTO2},
                headers=intern_headers,
            )
        assert resp.status_code == 409

    async def test_clock_in_rejected_if_pause_too_short(
        self, client: AsyncClient, intern_headers: dict
    ):
        """Règle 2 : refus si < 30 min depuis le dernier dépointage."""
        with mock_storage(), bypass_min_duration():
            await client.post("/api/v1/attendance/clock-in", files={"photo": FAKE_PHOTO}, headers=intern_headers)
            await client.post("/api/v1/attendance/clock-out", json={"note": VALID_NOTE}, headers=intern_headers)
            # Repointer immédiatement (pause = 0s < 30 min)
            resp = await client.post("/api/v1/attendance/clock-in", files={"photo": FAKE_PHOTO}, headers=intern_headers)
        assert resp.status_code == 400
        assert "30 min" in resp.json()["detail"]


class TestClockOut:

    async def test_clock_out_success(self, client: AsyncClient, intern_headers: dict):
        with mock_storage(), bypass_min_duration():
            await client.post(
                "/api/v1/attendance/clock-in",
                files={"photo": FAKE_PHOTO},
                headers=intern_headers,
            )
            resp = await client.post(
                "/api/v1/attendance/clock-out",
                json={"note": VALID_NOTE},
                headers=intern_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "CLOSED"
        assert data["clock_out_photo_id"] is None
        assert data["ended_at"] is not None
        assert data["note"] == VALID_NOTE

    async def test_clock_out_note_too_short(self, client: AsyncClient, intern_headers: dict):
        """Règle 4 : note < 200 caractères refusée."""
        with mock_storage(), bypass_min_duration():
            await client.post("/api/v1/attendance/clock-in", files={"photo": FAKE_PHOTO}, headers=intern_headers)
            resp = await client.post(
                "/api/v1/attendance/clock-out",
                json={"note": "Trop court"},
                headers=intern_headers,
            )
        assert resp.status_code == 400
        assert "200" in resp.json()["detail"]

    async def test_clock_out_too_soon(self, client: AsyncClient, intern_headers: dict):
        """Règle 3 : dépointage refusé si < 30 min depuis le pointage."""
        with mock_storage():
            await client.post("/api/v1/attendance/clock-in", files={"photo": FAKE_PHOTO}, headers=intern_headers)
            resp = await client.post(
                "/api/v1/attendance/clock-out",
                json={"note": VALID_NOTE},
                headers=intern_headers,
            )
        assert resp.status_code == 400
        assert "30 min" in resp.json()["detail"]

    async def test_clock_out_no_open_session(self, client: AsyncClient, intern_headers: dict):
        resp = await client.post(
            "/api/v1/attendance/clock-out",
            json={"note": VALID_NOTE},
            headers=intern_headers,
        )
        assert resp.status_code == 404

    async def test_clock_out_unauthenticated(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/attendance/clock-out",
            json={"note": VALID_NOTE},
        )
        assert resp.status_code == 401


class TestAdminLive:

    async def test_admin_live_returns_open_sessions(
        self, client: AsyncClient, admin_headers: dict, intern_headers: dict
    ):
        with mock_storage():
            await client.post(
                "/api/v1/attendance/clock-in",
                files={"photo": FAKE_PHOTO},
                headers=intern_headers,
            )
        resp = await client.get("/api/v1/attendance/admin/live", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["status"] == "OPEN"
        assert "clock_in_photo_id" in data[0]

    async def test_admin_live_forbidden_for_intern(self, client: AsyncClient, intern_headers: dict):
        resp = await client.get("/api/v1/attendance/admin/live", headers=intern_headers)
        assert resp.status_code == 403

    async def test_admin_live_empty(self, client: AsyncClient, admin_headers: dict):
        resp = await client.get("/api/v1/attendance/admin/live", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json() == []


class TestSummary:

    async def test_my_summary_empty(self, client: AsyncClient, intern_headers: dict):
        resp = await client.get("/api/v1/attendance/summary/me", headers=intern_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_hours"] == 0.0
        assert data["total_sessions"] == 0
        assert data["sessions"] == []

    async def test_my_summary_after_session(self, client: AsyncClient, intern_headers: dict):
        with mock_storage(), bypass_min_duration():
            await client.post("/api/v1/attendance/clock-in", files={"photo": FAKE_PHOTO}, headers=intern_headers)
            await client.post("/api/v1/attendance/clock-out", json={"note": VALID_NOTE}, headers=intern_headers)
        resp = await client.get("/api/v1/attendance/summary/me", headers=intern_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_sessions"] == 1
        assert data["total_hours"] >= 0
        assert len(data["sessions"]) == 1
        assert "clock_in" in data["sessions"][0]
        assert "clock_out" in data["sessions"][0]

    async def test_admin_summary_for_user(
        self, client: AsyncClient, admin_headers: dict, intern_user: User
    ):
        resp = await client.get(
            f"/api/v1/attendance/admin/summary/{intern_user.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["user_id"] == str(intern_user.id)

    async def test_summary_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/v1/attendance/summary/me")
        assert resp.status_code == 401
