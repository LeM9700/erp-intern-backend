"""Unit tests for app.core.security – hash, verify, JWT tokens."""
import pytest
from datetime import datetime, timezone

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)


# ── Password hashing ────────────────────────────────────────────────────────

class TestHashPassword:
    def test_hash_returns_bcrypt_string(self):
        h = hash_password("MyP@ss123")
        assert h.startswith("$2b$") or h.startswith("$2a$")

    def test_hash_differs_for_same_input(self):
        """Each call should produce a different salt."""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2

    def test_verify_correct_password(self):
        h = hash_password("correct")
        assert verify_password("correct", h) is True

    def test_verify_wrong_password(self):
        h = hash_password("correct")
        assert verify_password("wrong", h) is False

    def test_verify_empty_password(self):
        h = hash_password("")
        assert verify_password("", h) is True
        assert verify_password("notempty", h) is False


# ── Access token ─────────────────────────────────────────────────────────────

class TestAccessToken:
    def test_create_and_decode(self):
        token = create_access_token("user-123")
        payload = decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"

    def test_extra_claims(self):
        token = create_access_token("user-123", {"role": "ADMIN"})
        payload = decode_token(token)
        assert payload["role"] == "ADMIN"

    def test_expiration_is_in_future(self):
        token = create_access_token("user-123")
        payload = decode_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp > datetime.now(timezone.utc)


# ── Refresh token ────────────────────────────────────────────────────────────

class TestRefreshToken:
    def test_create_and_decode(self):
        token = create_refresh_token("user-456")
        payload = decode_token(token)
        assert payload["sub"] == "user-456"
        assert payload["type"] == "refresh"

    def test_expiration_is_in_future(self):
        token = create_refresh_token("user-456")
        payload = decode_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp > datetime.now(timezone.utc)


# ── Decode errors ────────────────────────────────────────────────────────────

class TestDecodeToken:
    def test_invalid_token_raises(self):
        with pytest.raises(ValueError, match="Invalid or expired token"):
            decode_token("not-a-jwt")

    def test_tampered_token_raises(self):
        token = create_access_token("user-1")
        with pytest.raises(ValueError):
            decode_token(token + "tampered")
