"""Integration tests for GET /api/v1/admin/dashboard."""
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.models.attendance import AttendanceSession, AttendanceStatus
from app.models.task import Task, TaskStatus, TaskPriority


FAKE_PHOTO = ("photo.jpg", b"fake-image-content", "image/jpeg")

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


class TestDashboardEndpoint:

    async def test_admin_gets_dashboard(
        self, client: AsyncClient, admin_headers: dict, intern_user: User
    ):
        resp = await client.get("/api/v1/admin/dashboard", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_interns" in data
        assert "active_interns" in data
        assert "live_sessions_count" in data
        assert "total_hours_this_week" in data
        assert "total_hours_this_month" in data
        assert "tasks_pending" in data
        assert "interns" in data
        assert isinstance(data["interns"], list)

    async def test_intern_forbidden(self, client: AsyncClient, intern_headers: dict):
        resp = await client.get("/api/v1/admin/dashboard", headers=intern_headers)
        assert resp.status_code == 403

    async def test_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/v1/admin/dashboard")
        assert resp.status_code == 401

    async def test_dashboard_shows_correct_intern_count(
        self,
        client: AsyncClient,
        admin_headers: dict,
        intern_user: User,
        intern_user2: User,
    ):
        resp = await client.get("/api/v1/admin/dashboard", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_interns"] == 2
        assert data["active_interns"] == 2
        assert len(data["interns"]) == 2

    async def test_dashboard_task_counts(
        self,
        client: AsyncClient,
        admin_headers: dict,
        intern_user: User,
    ):
        # Create tasks with different statuses
        await client.post(
            "/api/v1/tasks",
            json={"title": "Task pending", "assigned_to": [str(intern_user.id)]},
            headers=admin_headers,
        )
        await client.post(
            "/api/v1/tasks",
            json={"title": "Task pending 2"},
            headers=admin_headers,
        )

        resp = await client.get("/api/v1/admin/dashboard", headers=admin_headers)
        data = resp.json()
        assert data["tasks_pending"] >= 2

    async def test_dashboard_live_sessions(
        self,
        client: AsyncClient,
        admin_headers: dict,
        intern_headers: dict,
        intern_user: User,
    ):
        with mock_storage():
            await client.post(
                "/api/v1/attendance/clock-in",
                files={"photo": FAKE_PHOTO},
                headers=intern_headers,
            )

        resp = await client.get("/api/v1/admin/dashboard", headers=admin_headers)
        data = resp.json()
        assert data["live_sessions_count"] >= 1

    async def test_dashboard_intern_summary_shows_clocked_in(
        self,
        client: AsyncClient,
        admin_headers: dict,
        intern_headers: dict,
        intern_user: User,
    ):
        with mock_storage():
            await client.post(
                "/api/v1/attendance/clock-in",
                files={"photo": FAKE_PHOTO},
                headers=intern_headers,
            )

        resp = await client.get("/api/v1/admin/dashboard", headers=admin_headers)
        data = resp.json()
        intern_summary = next(
            (i for i in data["interns"] if i["user_id"] == str(intern_user.id)), None
        )
        assert intern_summary is not None
        assert intern_summary["is_currently_clocked_in"] is True

    async def test_dashboard_empty_state(
        self, client: AsyncClient, admin_headers: dict
    ):
        """Dashboard with no interns should return zeros."""
        resp = await client.get("/api/v1/admin/dashboard", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_interns"] == 0
        assert data["live_sessions_count"] == 0
        assert data["tasks_pending"] == 0
