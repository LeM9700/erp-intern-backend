"""Tests for GET /notifications, PATCH /notifications/{id}/read, PATCH /notifications/read-all"""
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def admin_notification(db_session: AsyncSession, admin_user: User) -> Notification:
    n = Notification(
        id=uuid.uuid4(),
        user_id=admin_user.id,
        title="Task Submitted",
        message="Task 'Fix bug' has been submitted for review.",
        is_read=False,
    )
    db_session.add(n)
    await db_session.commit()
    await db_session.refresh(n)
    return n


@pytest_asyncio.fixture
async def read_notification(db_session: AsyncSession, admin_user: User) -> Notification:
    n = Notification(
        id=uuid.uuid4(),
        user_id=admin_user.id,
        title="Already Read",
        message="This one was already read.",
        is_read=True,
    )
    db_session.add(n)
    await db_session.commit()
    await db_session.refresh(n)
    return n


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestListNotifications:

    async def test_list_returns_user_notifications(
        self, client: AsyncClient, admin_headers: dict, admin_notification: Notification
    ):
        response = await client.get("/api/v1/notifications", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == str(admin_notification.id)
        assert data["items"][0]["title"] == "Task Submitted"
        assert data["items"][0]["is_read"] is False

    async def test_list_returns_empty_when_no_notifications(
        self, client: AsyncClient, admin_headers: dict
    ):
        response = await client.get("/api/v1/notifications", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["items"] == []

    async def test_intern_sees_only_own_notifications(
        self,
        client: AsyncClient,
        intern_headers: dict,
        admin_notification: Notification,  # belongs to admin, not intern
    ):
        response = await client.get("/api/v1/notifications", headers=intern_headers)
        assert response.status_code == 200
        assert response.json()["items"] == []

    async def test_unauthenticated_is_rejected(self, client: AsyncClient):
        response = await client.get("/api/v1/notifications")
        assert response.status_code == 401


class TestMarkAsRead:

    async def test_mark_as_read_success(
        self, client: AsyncClient, admin_headers: dict, admin_notification: Notification
    ):
        response = await client.patch(
            f"/api/v1/notifications/{admin_notification.id}/read",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["is_read"] is True

    async def test_mark_other_user_notification_returns_404(
        self,
        client: AsyncClient,
        intern_headers: dict,
        admin_notification: Notification,  # belongs to admin
    ):
        response = await client.patch(
            f"/api/v1/notifications/{admin_notification.id}/read",
            headers=intern_headers,
        )
        assert response.status_code == 404

    async def test_mark_nonexistent_returns_404(
        self, client: AsyncClient, admin_headers: dict
    ):
        response = await client.patch(
            f"/api/v1/notifications/{uuid.uuid4()}/read",
            headers=admin_headers,
        )
        assert response.status_code == 404

    async def test_unauthenticated_is_rejected(
        self, client: AsyncClient, admin_notification: Notification
    ):
        response = await client.patch(
            f"/api/v1/notifications/{admin_notification.id}/read"
        )
        assert response.status_code == 401


class TestMarkAllAsRead:

    async def test_mark_all_as_read(
        self,
        client: AsyncClient,
        admin_headers: dict,
        admin_notification: Notification,
        read_notification: Notification,
    ):
        response = await client.patch(
            "/api/v1/notifications/read-all", headers=admin_headers
        )
        assert response.status_code == 200
        # Only the unread one should have been marked
        assert response.json()["marked_as_read"] == 1

    async def test_mark_all_when_none_unread(
        self, client: AsyncClient, admin_headers: dict, read_notification: Notification
    ):
        response = await client.patch(
            "/api/v1/notifications/read-all", headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["marked_as_read"] == 0

    async def test_unauthenticated_is_rejected(self, client: AsyncClient):
        response = await client.patch("/api/v1/notifications/read-all")
        assert response.status_code == 401
