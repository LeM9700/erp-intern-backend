"""Integration tests for /api/v1/users endpoints."""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class TestCreateUser:

    async def test_admin_creates_intern(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.post(
            "/api/v1/users/",
            json={
                "email": "newuser@test.com",
                "password": "Secret123!",
                "full_name": "New Intern",
                "role": "INTERN",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "newuser@test.com"
        assert data["full_name"] == "New Intern"
        assert data["role"] == "INTERN"
        assert data["is_active"] is True

    async def test_admin_creates_admin(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.post(
            "/api/v1/users/",
            json={
                "email": "admin2@test.com",
                "password": "AdminPass!",
                "full_name": "Admin 2",
                "role": "ADMIN",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "ADMIN"

    async def test_duplicate_email_409(
        self, client: AsyncClient, admin_headers: dict, intern_user: User
    ):
        resp = await client.post(
            "/api/v1/users/",
            json={
                "email": "intern@test.com",
                "password": "Secret123!",
                "full_name": "Dup",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 409

    async def test_intern_forbidden(self, client: AsyncClient, intern_headers: dict):
        resp = await client.post(
            "/api/v1/users/",
            json={
                "email": "x@test.com",
                "password": "Secret!",
                "full_name": "Nope",
            },
            headers=intern_headers,
        )
        assert resp.status_code == 403

    async def test_unauthenticated(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/users/",
            json={
                "email": "x@test.com",
                "password": "Secret!",
                "full_name": "Nope",
            },
        )
        assert resp.status_code == 401


class TestListUsers:

    async def test_admin_lists_users(
        self, client: AsyncClient, admin_headers: dict, intern_user: User
    ):
        resp = await client.get("/api/v1/users/", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "users" in data
        assert "total" in data
        assert data["total"] >= 2  # admin + intern

    async def test_filter_by_role(
        self, client: AsyncClient, admin_headers: dict, intern_user: User
    ):
        resp = await client.get(
            "/api/v1/users/?role=INTERN", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for u in data["users"]:
            assert u["role"] == "INTERN"

    async def test_intern_forbidden(self, client: AsyncClient, intern_headers: dict):
        resp = await client.get("/api/v1/users/", headers=intern_headers)
        assert resp.status_code == 403

    async def test_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/v1/users/")
        assert resp.status_code == 401


class TestGetUser:

    async def test_admin_gets_user_detail(
        self, client: AsyncClient, admin_headers: dict, intern_user: User
    ):
        resp = await client.get(
            f"/api/v1/users/{intern_user.id}", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "intern@test.com"
        assert data["id"] == str(intern_user.id)

    async def test_get_nonexistent_user(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.get(
            f"/api/v1/users/{uuid.uuid4()}", headers=admin_headers
        )
        assert resp.status_code == 404

    async def test_intern_forbidden(
        self, client: AsyncClient, intern_headers: dict, admin_user: User
    ):
        resp = await client.get(
            f"/api/v1/users/{admin_user.id}", headers=intern_headers
        )
        assert resp.status_code == 403


class TestUpdateUser:

    async def test_admin_updates_user(
        self, client: AsyncClient, admin_headers: dict, intern_user: User
    ):
        resp = await client.patch(
            f"/api/v1/users/{intern_user.id}",
            json={"full_name": "Updated Name"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Updated Name"

    async def test_update_email(
        self, client: AsyncClient, admin_headers: dict, intern_user: User
    ):
        resp = await client.patch(
            f"/api/v1/users/{intern_user.id}",
            json={"email": "newemail@test.com"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "newemail@test.com"

    async def test_intern_forbidden(
        self, client: AsyncClient, intern_headers: dict, admin_user: User
    ):
        resp = await client.patch(
            f"/api/v1/users/{admin_user.id}",
            json={"full_name": "Hack"},
            headers=intern_headers,
        )
        assert resp.status_code == 403


class TestDeactivateUser:

    async def test_admin_deactivates_user(
        self, client: AsyncClient, admin_headers: dict, intern_user: User
    ):
        resp = await client.delete(
            f"/api/v1/users/{intern_user.id}", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    async def test_deactivate_nonexistent(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.delete(
            f"/api/v1/users/{uuid.uuid4()}", headers=admin_headers
        )
        assert resp.status_code == 404

    async def test_intern_forbidden(
        self, client: AsyncClient, intern_headers: dict, admin_user: User
    ):
        resp = await client.delete(
            f"/api/v1/users/{admin_user.id}", headers=intern_headers
        )
        assert resp.status_code == 403
