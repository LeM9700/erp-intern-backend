import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api import auth, attendance, tasks, files, activity, users, notifications, dashboard
from app.core.security import hash_password
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.limiter import limiter

# Import all models so Alembic can detect them
from app.models.user import User  # noqa: F401
from app.models.attendance import AttendanceSession  # noqa: F401
from app.models.task import Task, TaskProof, TaskReview, TaskComment  # noqa: F401
from app.models.file import File  # noqa: F401
from app.models.activity import ActivityLog  # noqa: F401
from app.models.notification import Notification  # noqa: F401

logger = logging.getLogger(__name__)
settings = get_settings()

_INSECURE_JWT_DEFAULTS = {"change-me-in-production", "super-secret-change-me-in-production"}


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
        await asyncio.sleep(60)
        try:
            async with async_session_factory() as db:
                await AttendanceService.auto_close_expired_sessions(db)
                await db.commit()
        except Exception:
            logger.exception("Error in attendance auto-checker")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # JWT secret guard
    if settings.JWT_SECRET_KEY in _INSECURE_JWT_DEFAULTS:
        if settings.ENVIRONMENT == "production":
            raise RuntimeError(
                "JWT_SECRET_KEY must be changed before running in production. "
                "Set a strong random value in your .env file."
            )
        else:
            logger.warning(
                "JWT_SECRET_KEY is using an insecure default value. "
                "Change it before deploying to production."
            )
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
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Security headers middleware ──
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ── CORS middleware ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global exception handler ──
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
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
