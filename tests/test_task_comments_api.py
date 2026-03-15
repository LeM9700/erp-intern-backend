"""Integration tests for task comment endpoints."""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class TestAddComment:

    async def test_admin_adds_comment(
        self, client: AsyncClient, admin_headers: dict, intern_user: User
    ):
        # Create a task
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "Commentable task", "assigned_to": [str(intern_user.id)]},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/comments",
            json={"content": "Great progress!"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "Great progress!"
        assert data["task_id"] == task_id
        assert "author_id" in data
        assert "created_at" in data

    async def test_intern_adds_comment(
        self, client: AsyncClient, admin_headers: dict, intern_headers: dict, intern_user: User
    ):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "Intern comment task", "assigned_to": [str(intern_user.id)]},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/comments",
            json={"content": "I have a question about this task."},
            headers=intern_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["author_id"] == str(intern_user.id)

    async def test_comment_on_nonexistent_task(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.post(
            f"/api/v1/tasks/{uuid.uuid4()}/comments",
            json={"content": "Should fail"},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    async def test_unauthenticated(self, client: AsyncClient):
        resp = await client.post(
            f"/api/v1/tasks/{uuid.uuid4()}/comments",
            json={"content": "No auth"},
        )
        assert resp.status_code == 401


class TestListComments:

    async def test_list_comments(
        self, client: AsyncClient, admin_headers: dict, intern_headers: dict, intern_user: User
    ):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "Comment list task", "assigned_to": [str(intern_user.id)]},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]

        # Add two comments
        await client.post(
            f"/api/v1/tasks/{task_id}/comments",
            json={"content": "First comment"},
            headers=admin_headers,
        )
        await client.post(
            f"/api/v1/tasks/{task_id}/comments",
            json={"content": "Second comment"},
            headers=intern_headers,
        )

        resp = await client.get(
            f"/api/v1/tasks/{task_id}/comments",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["content"] == "First comment"
        assert data["items"][1]["content"] == "Second comment"

    async def test_list_comments_pagination(
        self, client: AsyncClient, admin_headers: dict
    ):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "Paginated comments"},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]

        # Add 3 comments
        for i in range(3):
            await client.post(
                f"/api/v1/tasks/{task_id}/comments",
                json={"content": f"Comment {i}"},
                headers=admin_headers,
            )

        resp = await client.get(
            f"/api/v1/tasks/{task_id}/comments?page=1&size=2",
            headers=admin_headers,
        )
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["size"] == 2
        assert data["pages"] == 2

    async def test_list_comments_empty(
        self, client: AsyncClient, admin_headers: dict
    ):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "No comments"},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]

        resp = await client.get(
            f"/api/v1/tasks/{task_id}/comments",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_unauthenticated(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/tasks/{uuid.uuid4()}/comments")
        assert resp.status_code == 401


class TestDeleteComment:

    async def test_author_deletes_own_comment(
        self, client: AsyncClient, admin_headers: dict
    ):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "Delete comment task"},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]

        comment_resp = await client.post(
            f"/api/v1/tasks/{task_id}/comments",
            json={"content": "To be deleted"},
            headers=admin_headers,
        )
        comment_id = comment_resp.json()["id"]

        resp = await client.delete(
            f"/api/v1/tasks/comments/{comment_id}",
            headers=admin_headers,
        )
        assert resp.status_code == 204

        # Verify it's gone
        list_resp = await client.get(
            f"/api/v1/tasks/{task_id}/comments",
            headers=admin_headers,
        )
        assert list_resp.json()["total"] == 0

    async def test_cannot_delete_others_comment(
        self, client: AsyncClient, admin_headers: dict, intern_headers: dict, intern_user: User
    ):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "Cross delete task", "assigned_to": [str(intern_user.id)]},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]

        # Admin creates comment
        comment_resp = await client.post(
            f"/api/v1/tasks/{task_id}/comments",
            json={"content": "Admin comment"},
            headers=admin_headers,
        )
        comment_id = comment_resp.json()["id"]

        # Intern tries to delete admin's comment
        resp = await client.delete(
            f"/api/v1/tasks/comments/{comment_id}",
            headers=intern_headers,
        )
        assert resp.status_code == 404

    async def test_delete_nonexistent_comment(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.delete(
            f"/api/v1/tasks/comments/{uuid.uuid4()}",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    async def test_unauthenticated(self, client: AsyncClient):
        resp = await client.delete(f"/api/v1/tasks/comments/{uuid.uuid4()}")
        assert resp.status_code == 401


class TestCommentNotifications:

    async def test_intern_comment_notifies_admins(
        self,
        client: AsyncClient,
        admin_headers: dict,
        intern_headers: dict,
        intern_user: User,
    ):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "Notify task", "assigned_to": [str(intern_user.id)]},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]

        # Intern adds comment
        await client.post(
            f"/api/v1/tasks/{task_id}/comments",
            json={"content": "Intern asks a question"},
            headers=intern_headers,
        )

        # Admin should see notification
        notif_resp = await client.get("/api/v1/notifications", headers=admin_headers)
        items = notif_resp.json()["items"]
        # Should have at least 1 notification about the comment
        # (could also have the assign notification, so filter)
        comment_notifs = [n for n in items if "commentaire" in n["title"].lower() or "comment" in n["title"].lower()]
        assert len(comment_notifs) >= 1

    async def test_admin_comment_notifies_intern(
        self,
        client: AsyncClient,
        admin_headers: dict,
        intern_headers: dict,
        intern_user: User,
    ):
        create = await client.post(
            "/api/v1/tasks",
            json={"title": "Admin notify task", "assigned_to": [str(intern_user.id)]},
            headers=admin_headers,
        )
        task_id = create.json()[0]["id"]

        # Admin adds comment
        await client.post(
            f"/api/v1/tasks/{task_id}/comments",
            json={"content": "Good work so far"},
            headers=admin_headers,
        )

        # Intern should see notification
        notif_resp = await client.get("/api/v1/notifications", headers=intern_headers)
        items = notif_resp.json()["items"]
        comment_notifs = [n for n in items if "commentaire" in n["title"].lower() or "comment" in n["title"].lower()]
        assert len(comment_notifs) >= 1
