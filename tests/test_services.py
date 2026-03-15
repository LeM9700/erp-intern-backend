"""Unit tests for service layer (AuthService, AttendanceService, TaskService, ActivityLogService)."""
import io
import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.models.file import File
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.attendance import AttendanceSession, AttendanceStatus
from app.models.activity import ActivityLog, ActivityAction
from app.core.security import hash_password
from app.services.auth_service import AuthService
from app.services.attendance_service import AttendanceService
from app.services.task_service import TaskService
from app.services.activity_service import ActivityLogService
from app.schemas.task import TaskCreate, TaskUpdate


def _fake_photo(name="photo.jpg", content_type="image/jpeg") -> UploadFile:
    """Create a fake UploadFile for testing."""
    return UploadFile(
        filename=name,
        file=io.BytesIO(b"fake-image-content"),
        headers={"content-type": content_type},
    )


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
    return patch("app.services.attendance_service.MIN_DURATION_BEFORE_CLOCKOUT", timedelta(0))


def bypass_pause_rule():
    return patch("app.services.attendance_service.MIN_PAUSE_BEFORE_RECLOCKING", timedelta(0))


# ═══════════════════════════════════════════════════════════════════════════
# AuthService
# ═══════════════════════════════════════════════════════════════════════════

class TestAuthService:
    @pytest.mark.asyncio
    async def test_authenticate_success(self, db_session: AsyncSession, admin_user: User):
        result = await AuthService.authenticate(db_session, "admin@test.com", "Admin123!")
        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "bearer"

    @pytest.mark.asyncio
    async def test_authenticate_wrong_password(self, db_session: AsyncSession, admin_user: User):
        with pytest.raises(ValueError, match="Invalid email or password"):
            await AuthService.authenticate(db_session, "admin@test.com", "WrongPass!")

    @pytest.mark.asyncio
    async def test_authenticate_unknown_email(self, db_session: AsyncSession):
        with pytest.raises(ValueError, match="Invalid email or password"):
            await AuthService.authenticate(db_session, "nobody@test.com", "pass")

    @pytest.mark.asyncio
    async def test_authenticate_inactive_user(self, db_session: AsyncSession):
        user = User(
            email="inactive@test.com",
            hashed_password=hash_password("Pass123!"),
            full_name="Inactive",
            role=UserRole.INTERN,
            is_active=False,
        )
        db_session.add(user)
        await db_session.commit()
        with pytest.raises(ValueError, match="Invalid email or password"):
            await AuthService.authenticate(db_session, "inactive@test.com", "Pass123!")

    @pytest.mark.asyncio
    async def test_refresh_success(self, db_session: AsyncSession, admin_user: User):
        tokens = await AuthService.authenticate(db_session, "admin@test.com", "Admin123!")
        new_tokens = await AuthService.refresh(db_session, tokens.refresh_token)
        assert new_tokens.access_token
        assert new_tokens.refresh_token

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, db_session: AsyncSession):
        with pytest.raises(ValueError, match="Invalid or expired refresh token"):
            await AuthService.refresh(db_session, "invalid-token")

    @pytest.mark.asyncio
    async def test_refresh_with_access_token_fails(self, db_session: AsyncSession, admin_user: User):
        tokens = await AuthService.authenticate(db_session, "admin@test.com", "Admin123!")
        with pytest.raises(ValueError, match="Invalid token type"):
            await AuthService.refresh(db_session, tokens.access_token)


# ═══════════════════════════════════════════════════════════════════════════
# ActivityLogService
# ═══════════════════════════════════════════════════════════════════════════

class TestActivityLogService:
    @pytest.mark.asyncio
    async def test_log_creates_entry(self, db_session: AsyncSession, intern_user: User):
        entry = await ActivityLogService.log(
            db_session,
            user_id=intern_user.id,
            action=ActivityAction.CLOCK_IN,
            entity_type="AttendanceSession",
            detail="Clocked in",
        )
        assert entry.id is not None
        assert entry.user_id == intern_user.id
        assert entry.action == ActivityAction.CLOCK_IN
        assert entry.detail == "Clocked in"

    @pytest.mark.asyncio
    async def test_log_with_entity_id(self, db_session: AsyncSession, intern_user: User):
        entity_id = uuid.uuid4()
        entry = await ActivityLogService.log(
            db_session,
            user_id=intern_user.id,
            action=ActivityAction.FILE_UPLOAD,
            entity_id=entity_id,
            entity_type="File",
        )
        assert entry.entity_id == entity_id


# ═══════════════════════════════════════════════════════════════════════════
# AttendanceService
# ═══════════════════════════════════════════════════════════════════════════

class TestAttendanceService:
    @pytest.mark.asyncio
    async def test_clock_in_success(
        self, db_session: AsyncSession, intern_user: User
    ):
        photo = _fake_photo()
        with mock_storage():
            session = await AttendanceService.clock_in(db_session, intern_user.id, photo)
        assert session.user_id == intern_user.id
        assert session.status == AttendanceStatus.OPEN
        assert session.clock_in_photo_id is not None

    @pytest.mark.asyncio
    async def test_clock_in_invalid_content_type(self, db_session: AsyncSession, intern_user: User):
        photo = _fake_photo(content_type="text/plain")
        with mock_storage(), pytest.raises(ValueError, match="Invalid file type"):
            await AttendanceService.clock_in(db_session, intern_user.id, photo)

    @pytest.mark.asyncio
    async def test_clock_in_already_open(
        self, db_session: AsyncSession, intern_user: User
    ):
        with mock_storage():
            await AttendanceService.clock_in(db_session, intern_user.id, _fake_photo())
        with mock_storage(), pytest.raises(HTTPException) as exc_info:
            await AttendanceService.clock_in(db_session, intern_user.id, _fake_photo())
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_clock_out_success(
        self, db_session: AsyncSession, intern_user: User
    ):
        note = "A" * 200
        with mock_storage(), bypass_min_duration():
            await AttendanceService.clock_in(db_session, intern_user.id, _fake_photo())
            session = await AttendanceService.clock_out(db_session, intern_user.id, _fake_photo(), note)
        assert session.status == AttendanceStatus.CLOSED
        assert session.clock_out_photo_id is not None
        assert session.ended_at is not None

    @pytest.mark.asyncio
    async def test_clock_out_no_open_session(
        self, db_session: AsyncSession, intern_user: User
    ):
        note = "A" * 200
        with mock_storage(), pytest.raises(HTTPException) as exc_info:
            await AttendanceService.clock_out(db_session, intern_user.id, _fake_photo(), note)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_live_sessions(
        self, db_session: AsyncSession, intern_user: User
    ):
        with mock_storage():
            await AttendanceService.clock_in(db_session, intern_user.id, _fake_photo())
        live = await AttendanceService.get_live_sessions(db_session)
        assert len(live) == 1
        assert live[0].user_id == intern_user.id

    @pytest.mark.asyncio
    async def test_get_live_sessions_empty(self, db_session: AsyncSession):
        live = await AttendanceService.get_live_sessions(db_session)
        assert live == []


# ═══════════════════════════════════════════════════════════════════════════
# TaskService
# ═══════════════════════════════════════════════════════════════════════════

class TestTaskService:
    @pytest.mark.asyncio
    async def test_create_task(self, db_session: AsyncSession, admin_user: User, intern_user: User):
        data = TaskCreate(
            title="Test Task",
            description="Do something",
            priority=TaskPriority.HIGH,
            assigned_to=[intern_user.id],
        )
        tasks = await TaskService.create_task(db_session, data, admin_user.id)
        assert len(tasks) == 1
        task = tasks[0]
        assert task.title == "Test Task"
        assert task.created_by == admin_user.id
        assert task.assigned_to == intern_user.id
        assert task.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_update_task(self, db_session: AsyncSession, admin_user: User):
        data = TaskCreate(title="Old Title")
        tasks = await TaskService.create_task(db_session, data, admin_user.id)
        task = tasks[0]

        updated = await TaskService.update_task(
            db_session, task.id, TaskUpdate(title="New Title", priority=TaskPriority.LOW)
        )
        assert updated.title == "New Title"
        assert updated.priority == TaskPriority.LOW

    @pytest.mark.asyncio
    async def test_update_task_not_found(self, db_session: AsyncSession):
        with pytest.raises(HTTPException) as exc_info:
            await TaskService.update_task(db_session, uuid.uuid4(), TaskUpdate(title="x"))
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_approved_task_fails(self, db_session: AsyncSession, admin_user: User):
        data = TaskCreate(title="Approved")
        tasks = await TaskService.create_task(db_session, data, admin_user.id)
        task = tasks[0]
        task.status = TaskStatus.APPROVED
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await TaskService.update_task(db_session, task.id, TaskUpdate(title="Nope"))
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_list_admin_tasks(self, db_session: AsyncSession, admin_user: User):
        await TaskService.create_task(db_session, TaskCreate(title="T1"), admin_user.id)
        await TaskService.create_task(db_session, TaskCreate(title="T2"), admin_user.id)
        tasks, total = await TaskService.list_admin_tasks(db_session)
        assert len(tasks) == 2
        assert total == 2

    @pytest.mark.asyncio
    async def test_list_intern_tasks(self, db_session: AsyncSession, admin_user: User, intern_user: User):
        await TaskService.create_task(
            db_session, TaskCreate(title="Assigned", assigned_to=[intern_user.id]), admin_user.id
        )
        await TaskService.create_task(
            db_session, TaskCreate(title="Not assigned"), admin_user.id
        )
        tasks, total = await TaskService.list_intern_tasks(db_session, intern_user.id)
        assert len(tasks) == 1
        assert total == 1
        assert tasks[0].title == "Assigned"

    @pytest.mark.asyncio
    async def test_start_task_success(self, db_session: AsyncSession, admin_user: User, intern_user: User):
        tasks = await TaskService.create_task(
            db_session, TaskCreate(title="Start me", assigned_to=[intern_user.id]), admin_user.id
        )
        started = await TaskService.start_task(db_session, tasks[0].id, intern_user.id)
        assert started.status == TaskStatus.IN_PROGRESS
        assert started.started_at is not None

    @pytest.mark.asyncio
    async def test_start_task_not_pending_fails(self, db_session: AsyncSession, admin_user: User, intern_user: User):
        tasks = await TaskService.create_task(
            db_session, TaskCreate(title="Started", assigned_to=[intern_user.id]), admin_user.id
        )
        task = tasks[0]
        await TaskService.start_task(db_session, task.id, intern_user.id)
        with pytest.raises(HTTPException) as exc_info:
            await TaskService.start_task(db_session, task.id, intern_user.id)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_start_task_not_found(self, db_session: AsyncSession, intern_user: User):
        with pytest.raises(HTTPException) as exc_info:
            await TaskService.start_task(db_session, uuid.uuid4(), intern_user.id)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_submit_task_success(
        self, db_session: AsyncSession, admin_user: User, intern_user: User
    ):
        tasks = await TaskService.create_task(
            db_session, TaskCreate(title="Submit me", assigned_to=[intern_user.id]), admin_user.id
        )
        task = tasks[0]
        await TaskService.start_task(db_session, task.id, intern_user.id)
        submitted = await TaskService.submit_task(
            db_session, task.id, intern_user.id,
            note="Here is proof",
            proof_url="https://github.com/example/proof",
        )
        assert submitted.status == TaskStatus.SUBMITTED
        assert submitted.submitted_at is not None

    @pytest.mark.asyncio
    async def test_submit_task_pending_fails(
        self, db_session: AsyncSession, admin_user: User, intern_user: User
    ):
        tasks = await TaskService.create_task(
            db_session, TaskCreate(title="Pending", assigned_to=[intern_user.id]), admin_user.id
        )
        with pytest.raises(HTTPException) as exc_info:
            await TaskService.submit_task(
                db_session, tasks[0].id, intern_user.id,
                note="proof", proof_url="https://example.com",
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_submit_task_no_proof_fails(
        self, db_session: AsyncSession, admin_user: User, intern_user: User
    ):
        tasks = await TaskService.create_task(
            db_session, TaskCreate(title="No proof", assigned_to=[intern_user.id]), admin_user.id
        )
        task = tasks[0]
        await TaskService.start_task(db_session, task.id, intern_user.id)
        with pytest.raises(HTTPException) as exc_info:
            await TaskService.submit_task(
                db_session, task.id, intern_user.id, note="proof"
            )
        assert exc_info.value.status_code == 422
