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
