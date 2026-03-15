"""Integration tests for /api/v1/activity endpoints."""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.file import File
from app.models.activity import ActivityLog, ActivityAction


class TestListAllActivity:
    @pytest.mark.asyncio
    async def test_admin_can_list_all_activity(
        self, client: AsyncClient, admin_headers: dict, db_session: AsyncSession, admin_user: User
    ):
        # Seed some activity
        log = ActivityLog(
            user_id=admin_user.id,
            action=ActivityAction.CLOCK_IN,
            detail="Test clock in",
        )
        db_session.add(log)
        await db_session.commit()

        resp = await client.get("/api/v1/activity", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) >= 1

    @pytest.mark.asyncio
    async def test_intern_forbidden_all_activity(
        self, client: AsyncClient, intern_headers: dict
    ):
        resp = await client.get("/api/v1/activity", headers=intern_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_all_activity(self, client: AsyncClient):
        resp = await client.get("/api/v1/activity")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_activity_list(self, client: AsyncClient, admin_headers: dict):
        resp = await client.get("/api/v1/activity", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0


class TestListMyActivity:
    @pytest.mark.asyncio
    async def test_intern_can_list_own_activity(
        self, client: AsyncClient, intern_headers: dict, db_session: AsyncSession, intern_user: User
    ):
        log = ActivityLog(
            user_id=intern_user.id,
            action=ActivityAction.TASK_START,
            detail="Started a task",
        )
        db_session.add(log)
        await db_session.commit()

        resp = await client.get("/api/v1/activity/me", headers=intern_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 1
        assert data["items"][0]["user_id"] == str(intern_user.id)

    @pytest.mark.asyncio
    async def test_admin_can_list_own_activity(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.get("/api/v1/activity/me", headers=admin_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["items"], list)

    @pytest.mark.asyncio
    async def test_my_activity_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/v1/activity/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_my_activity_only_shows_own(
        self,
        client: AsyncClient,
        intern_headers: dict,
        db_session: AsyncSession,
        intern_user: User,
        admin_user: User,
    ):
        # Create logs for both users
        db_session.add(ActivityLog(
            user_id=intern_user.id, action=ActivityAction.CLOCK_IN, detail="intern log"
        ))
        db_session.add(ActivityLog(
            user_id=admin_user.id, action=ActivityAction.CLOCK_IN, detail="admin log"
        ))
        await db_session.commit()

        resp = await client.get("/api/v1/activity/me", headers=intern_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Should only contain intern's logs
        for entry in data["items"]:
            assert entry["user_id"] == str(intern_user.id)
