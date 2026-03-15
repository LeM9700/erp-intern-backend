import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import bcrypt as _bcrypt

from app.models.user import User
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token, validate_password_strength
from app.schemas.auth import TokenResponse

# Generated once at import time. Running bcrypt against this when the user doesn't exist
# ensures response time is indistinguishable from a real (failed) password check.
_DUMMY_HASH: str = _bcrypt.hashpw(b"__dummy_sentinel__", _bcrypt.gensalt(rounds=12)).decode()


class AuthService:

    @staticmethod
    async def authenticate(db: AsyncSession, email: str, password: str) -> TokenResponse:
        result = await db.execute(select(User).where(User.email == email, User.is_active.is_(True)))
        user = result.scalar_one_or_none()

        # Always run bcrypt to prevent timing-based user enumeration.
        hash_to_check = user.hashed_password if user else _DUMMY_HASH
        password_valid = verify_password(password, hash_to_check)

        if not user or not password_valid:
            raise ValueError("Invalid email or password")

        access = create_access_token(str(user.id), {"role": user.role.value})
        refresh = create_refresh_token(str(user.id))
        return TokenResponse(access_token=access, refresh_token=refresh)

    @staticmethod
    async def refresh(db: AsyncSession, refresh_token: str) -> TokenResponse:
        try:
            payload = decode_token(refresh_token)
        except ValueError:
            raise ValueError("Invalid or expired refresh token")

        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type")

        user_id = payload.get("sub")
        result = await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("User not found or inactive")

        access = create_access_token(str(user.id), {"role": user.role.value})
        new_refresh = create_refresh_token(str(user.id))
        return TokenResponse(access_token=access, refresh_token=new_refresh)

    @staticmethod
    async def change_password(
        db: AsyncSession, user: User, current_password: str, new_password: str
    ) -> None:
        if not verify_password(current_password, user.hashed_password):
            raise ValueError("Mot de passe actuel incorrect")
        validate_password_strength(new_password)
        user.hashed_password = hash_password(new_password)
        await db.flush()
