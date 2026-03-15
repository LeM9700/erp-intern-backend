"""Integration tests for PUT /api/v1/auth/change-password."""
import pytest
from httpx import AsyncClient

from app.models.user import User


class TestChangePassword:

    async def test_change_password_success(
        self, client: AsyncClient, intern_headers: dict
    ):
        resp = await client.put(
            "/api/v1/auth/change-password",
            json={"current_password": "Intern123!", "new_password": "NewPass123!"},
            headers=intern_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Mot de passe modifié avec succès"

        # Verify login with new password works
        resp2 = await client.post(
            "/api/v1/auth/login",
            json={"email": "intern@test.com", "password": "NewPass123!"},
        )
        assert resp2.status_code == 200
        assert "access_token" in resp2.json()

    async def test_change_password_wrong_current(
        self, client: AsyncClient, intern_headers: dict
    ):
        resp = await client.put(
            "/api/v1/auth/change-password",
            json={"current_password": "WrongPassword!", "new_password": "NewPass123!"},
            headers=intern_headers,
        )
        assert resp.status_code == 400
        assert "incorrect" in resp.json()["detail"].lower()

    async def test_change_password_too_short(
        self, client: AsyncClient, intern_headers: dict
    ):
        resp = await client.put(
            "/api/v1/auth/change-password",
            json={"current_password": "Intern123!", "new_password": "abc"},
            headers=intern_headers,
        )
        assert resp.status_code == 400
        assert "8" in resp.json()["detail"]

    async def test_change_password_unauthenticated(self, client: AsyncClient):
        resp = await client.put(
            "/api/v1/auth/change-password",
            json={"current_password": "x", "new_password": "y"},
        )
        assert resp.status_code == 401

    async def test_change_password_admin(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.put(
            "/api/v1/auth/change-password",
            json={"current_password": "Admin123!", "new_password": "NewAdmin123!"},
            headers=admin_headers,
        )
        assert resp.status_code == 200

    async def test_old_password_fails_after_change(
        self, client: AsyncClient, intern_headers: dict
    ):
        # Change the password
        await client.put(
            "/api/v1/auth/change-password",
            json={"current_password": "Intern123!", "new_password": "NewPass123!"},
            headers=intern_headers,
        )
        # Old password should fail
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "intern@test.com", "password": "Intern123!"},
        )
        assert resp.status_code == 401
