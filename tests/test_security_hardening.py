from app.core.config import Settings


def test_settings_cors_defaults():
    s = Settings()
    assert isinstance(s.CORS_ORIGINS, list)
    assert len(s.CORS_ORIGINS) > 0


def test_settings_cors_from_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["https://myapp.com"]')
    s = Settings()
    assert s.CORS_ORIGINS == ["https://myapp.com"]


def test_settings_environment_default():
    s = Settings()
    assert s.ENVIRONMENT == "development"
