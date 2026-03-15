def test_async_database_url_uses_railway_injection(monkeypatch):
    """Si DATABASE_URL est injecté (Railway), l'app le convertit en asyncpg://."""
    from app.core.config import Settings
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/mydb")
    s = Settings()
    assert s.ASYNC_DATABASE_URL == "postgresql+asyncpg://user:pass@host:5432/mydb"


def test_async_database_url_already_asyncpg(monkeypatch):
    """Si DATABASE_URL est déjà asyncpg, il passe sans modification."""
    from app.core.config import Settings
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@host:5432/mydb")
    s = Settings()
    assert s.ASYNC_DATABASE_URL == "postgresql+asyncpg://user:pass@host:5432/mydb"


def test_async_database_url_fallback_to_parts(monkeypatch):
    """Sans DATABASE_URL, construit depuis POSTGRES_* vars."""
    from app.core.config import Settings
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings(
        POSTGRES_USER="myuser",
        POSTGRES_PASSWORD="mypass",
        POSTGRES_HOST="myhost",
        POSTGRES_PORT=5432,
        POSTGRES_DB="mydb",
    )
    assert s.ASYNC_DATABASE_URL == "postgresql+asyncpg://myuser:mypass@myhost:5432/mydb"
