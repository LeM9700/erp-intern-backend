import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api import auth, attendance, tasks, files, activity, users, notifications, dashboard
from app.core.security import hash_password

# Import all models so Alembic can detect them
from app.models.user import User  # noqa: F401
from app.models.attendance import AttendanceSession  # noqa: F401
from app.models.task import Task, TaskProof, TaskReview, TaskComment  # noqa: F401
from app.models.file import File  # noqa: F401
from app.models.activity import ActivityLog  # noqa: F401
from app.models.notification import Notification  # noqa: F401

settings = get_settings()


async def seed_admin():
    """Create a default ADMIN user if none exists."""
    from app.db.session import async_session_factory
    from sqlalchemy import select
    from app.models.user import User, UserRole

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.role == UserRole.ADMIN).limit(1))
        if result.scalar_one_or_none() is None:
            admin = User(
                email="admin@erp.local",
                hashed_password=hash_password("admin123"),
                full_name="Admin User",
                role=UserRole.ADMIN,
            )
            session.add(admin)
            await session.commit()


async def _attendance_checker():
    """Règle 1 : ferme automatiquement les sessions ouvertes depuis plus de 4h30."""
    from app.db.session import async_session_factory
    from app.services.attendance_service import AttendanceService
    while True:
        await asyncio.sleep(60)  # Vérifie toutes les minutes
        try:
            async with async_session_factory() as db:
                await AttendanceService.auto_close_expired_sessions(db)
                await db.commit()
        except Exception:
            pass  # Ne pas crasher l'app


@asynccontextmanager
async def lifespan(app: FastAPI):
    await seed_admin()
    checker = asyncio.create_task(_attendance_checker())
    yield
    checker.cancel()
    try:
        await checker
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
)

# ── CORS middleware ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production, listez les domaines autorisés
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Register routers
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(attendance.router, prefix=settings.API_V1_PREFIX)
app.include_router(tasks.router, prefix=settings.API_V1_PREFIX)
app.include_router(files.router, prefix=settings.API_V1_PREFIX)
app.include_router(activity.router, prefix=settings.API_V1_PREFIX)
app.include_router(notifications.router, prefix=settings.API_V1_PREFIX)
app.include_router(dashboard.router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok"}
