from app.core.config import Settings


def test_settings_cors_defaults():
    s = Settings()
    assert s.CORS_ORIGINS == ["http://localhost:3000", "http://localhost:8080"]


def test_settings_cors_from_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["https://myapp.com"]')
    s = Settings()
    assert s.CORS_ORIGINS == ["https://myapp.com"]


def test_settings_environment_default():
    s = Settings()
    assert s.ENVIRONMENT == "development"


def test_settings_environment_from_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    s = Settings()
    assert s.ENVIRONMENT == "production"


from fastapi.testclient import TestClient
import logging


def test_cors_headers_present():
    """CORS response header reflects configured origin."""
    from app.main import app
    client = TestClient(app)
    response = client.options(
        "/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" in response.headers


def test_security_headers_present():
    from app.main import app
    client = TestClient(app)
    response = client.get("/health")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


def test_global_exception_handler_logs(caplog):
    """Unhandled exceptions are logged, not swallowed silently."""
    from app.main import app
    from fastapi import Request

    async def boom(request: Request):
        raise RuntimeError("test error")

    app.add_route("/test-boom", boom)
    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = client.get("/test-boom")
    assert response.status_code == 500
    assert "test-boom" in caplog.text or "test error" in caplog.text


# ── Task 4: Rate limiting ──

def test_login_rate_limit_responds_normally():
    """Login endpoint responds with 401 for bad credentials (not 429 on first attempt)."""
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@test.com", "password": "wrongpass"},
    )
    assert response.status_code == 401


# ── Task 5: User enumeration fix ──

import time
import pytest


@pytest.mark.asyncio
async def test_login_timing_similar_for_unknown_user(db_session):
    """Unknown email path must run bcrypt (not skip it) — must take > 10ms."""
    from app.services.auth_service import AuthService
    t0 = time.monotonic()
    with pytest.raises(ValueError):
        await AuthService.authenticate(db_session, "nobody@example.com", "somepassword")
    t_unknown = time.monotonic() - t0
    assert t_unknown > 0.01, f"Unknown user path appears to skip bcrypt (took {t_unknown:.3f}s)"


# ── Task 6: Password strength validation ──

def test_password_too_short_rejected():
    from app.core.security import validate_password_strength
    with pytest.raises(ValueError, match="8"):
        validate_password_strength("abc123")


def test_password_exactly_8_chars_accepted():
    from app.core.security import validate_password_strength
    validate_password_strength("abcd1234")  # should not raise


# ── Task 7: MIME validation on file upload ──

import io


@pytest.mark.asyncio
async def test_upload_rejects_non_image_mime(client, intern_token):
    """Uploading a non-image file should return 400."""
    fake_pdf = io.BytesIO(b"%PDF-1.4 fake content")
    response = await client.post(
        "/api/v1/files/upload",
        headers={"Authorization": f"Bearer {intern_token}"},
        files={"file": ("document.pdf", fake_pdf, "application/pdf")},
    )
    assert response.status_code == 400
