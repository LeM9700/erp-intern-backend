"""Integration tests for /api/v1/tasks endpoints."""
import uuid
import pytest
from httpx import AsyncClient

from app.models.user import User
from app.models.task import TaskStatus, TaskPriority


class TestCreateTask:
    @pytest.mark.asyncio
    async def test_create_task_as_admin(
        self, client: AsyncClient, admin_headers: dict, intern_user: User
    ):
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "title": "Write report",
                "description": "Quarterly report",
                "priority": "HIGH",
                "assigned_to": [str(intern_user.id)],
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Write report"
        assert data[0]["priority"] == "HIGH"
        assert data[0]["status"] == "PENDING"
        assert data[0]["assigned_to"] == str(intern_user.id)

    @pytest.mark.asyncio
    async def test_create_task_multi_intern(
        self, client: AsyncClient, admin_headers: dict, intern_user: User, intern_user2: User
    ):
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "title": "Shared task",
                "assigned_to": [str(intern_user.id), str(intern_user2.id)],
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 2
        assignees = {t["assigned_to"] for t in data}
        assert str(intern_user.id) in assignees
        assert str(intern_user2.id) in assignees

    @pytest.mark.asyncio
    async def test_create_task_forbidden_for_intern(
        self, client: AsyncClient, intern_headers: dict
    ):
        resp = await client.post(
            "/api/v1/tasks",
            json={"title": "Nope"},
            headers=intern_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_task_unauthenticated(self, client: AsyncClient):
        resp = await client.post("/api/v1/tasks", json={"title": "x"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_task_minimal(self, client: AsyncClient, admin_headers: dict):
        resp = await client.post(
            "/api/v1/tasks",
            json={"title": "Minimal task"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["priority"] == "MEDIUM"  # default
        assert data[0]["assigned_to"] is None


class TestUpdateTask:
    @pytest.mark.asyncio
    async def test_update_task_as_admin(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "Original"},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"title": "Updated", "priority": "LOW"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated"
        assert resp.json()["priority"] == "LOW"

    @pytest.mark.asyncio
    async def test_update_task_not_found(self, client: AsyncClient, admin_headers: dict):
        resp = await client.patch(
            f"/api/v1/tasks/{uuid.uuid4()}",
            json={"title": "x"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_task_forbidden_for_intern(
        self, client: AsyncClient, admin_headers: dict, intern_headers: dict
    ):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "Admin task"},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"title": "Hacked"},
            headers=intern_headers,
        )
        assert resp.status_code == 403


class TestListTasks:
    @pytest.mark.asyncio
    async def test_list_admin_tasks(self, client: AsyncClient, admin_headers: dict):
        await client.post("/api/v1/tasks", json={"title": "T1"}, headers=admin_headers)
        await client.post("/api/v1/tasks", json={"title": "T2"}, headers=admin_headers)

        resp = await client.get("/api/v1/tasks/admin", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 2
        assert data["total"] >= 2

    @pytest.mark.asyncio
    async def test_list_admin_tasks_forbidden_for_intern(
        self, client: AsyncClient, intern_headers: dict
    ):
        resp = await client.get("/api/v1/tasks/admin", headers=intern_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_list_my_tasks(
        self, client: AsyncClient, admin_headers: dict, intern_headers: dict, intern_user: User
    ):
        await client.post(
            "/api/v1/tasks",
            json={"title": "For intern", "assigned_to": [str(intern_user.id)]},
            headers=admin_headers,
        )
        await client.post(
            "/api/v1/tasks",
            json={"title": "Not for intern"},
            headers=admin_headers,
        )

        resp = await client.get("/api/v1/tasks/me", headers=intern_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "For intern"

    @pytest.mark.asyncio
    async def test_list_my_tasks_forbidden_for_admin(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.get("/api/v1/tasks/me", headers=admin_headers)
        assert resp.status_code == 403


class TestStartTask:
    @pytest.mark.asyncio
    async def test_start_task(
        self, client: AsyncClient, admin_headers: dict, intern_headers: dict, intern_user: User
    ):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "Start me", "assigned_to": [str(intern_user.id)]},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}/start",
            headers=intern_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "IN_PROGRESS"
        assert resp.json()["started_at"] is not None

    @pytest.mark.asyncio
    async def test_start_task_already_started(
        self, client: AsyncClient, admin_headers: dict, intern_headers: dict, intern_user: User
    ):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "Already started", "assigned_to": [str(intern_user.id)]},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]
        await client.patch(f"/api/v1/tasks/{task_id}/start", headers=intern_headers)

        resp = await client.patch(f"/api/v1/tasks/{task_id}/start", headers=intern_headers)
        assert resp.status_code == 400


class TestSubmitTask:
    @pytest.mark.asyncio
    async def test_submit_task_with_url(
        self,
        client: AsyncClient,
        admin_headers: dict,
        intern_headers: dict,
        intern_user: User,
    ):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "Submit me", "assigned_to": [str(intern_user.id)]},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]
        await client.patch(f"/api/v1/tasks/{task_id}/start", headers=intern_headers)

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/submit",
            data={"note": "Done!", "proof_url": "https://github.com/example/proof"},
            headers=intern_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUBMITTED"
        assert len(data["proofs"]) == 1
        assert data["proofs"][0]["proof_url"] == "https://github.com/example/proof"
        assert data["proofs"][0]["file_id"] is None

    @pytest.mark.asyncio
    async def test_submit_task_with_file(
        self,
        client: AsyncClient,
        admin_headers: dict,
        intern_headers: dict,
        intern_user: User,
    ):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "File submit", "assigned_to": [str(intern_user.id)]},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]
        await client.patch(f"/api/v1/tasks/{task_id}/start", headers=intern_headers)

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/submit",
            data={"note": "Here is my proof"},
            files={"proof_file": ("proof.pdf", b"%PDF-1.4 test", "application/pdf")},
            headers=intern_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUBMITTED"
        assert data["proofs"][0]["file_id"] is not None
        assert data["proofs"][0]["proof_url"] is None

    @pytest.mark.asyncio
    async def test_submit_task_no_proof(
        self,
        client: AsyncClient,
        admin_headers: dict,
        intern_headers: dict,
        intern_user: User,
    ):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "No proof", "assigned_to": [str(intern_user.id)]},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]
        await client.patch(f"/api/v1/tasks/{task_id}/start", headers=intern_headers)

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/submit",
            data={"note": "Oops"},
            headers=intern_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_task_invalid_url(
        self,
        client: AsyncClient,
        admin_headers: dict,
        intern_headers: dict,
        intern_user: User,
    ):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "Bad URL", "assigned_to": [str(intern_user.id)]},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]
        await client.patch(f"/api/v1/tasks/{task_id}/start", headers=intern_headers)

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/submit",
            data={"note": "Bad link", "proof_url": "not-a-url"},
            headers=intern_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_task_not_started(
        self,
        client: AsyncClient,
        admin_headers: dict,
        intern_headers: dict,
        intern_user: User,
    ):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "Not started", "assigned_to": [str(intern_user.id)]},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/submit",
            data={"note": "proof", "proof_url": "https://example.com"},
            headers=intern_headers,
        )
        assert resp.status_code == 400
