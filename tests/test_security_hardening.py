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
