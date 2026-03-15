from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.core.security import hash_password


class UserService:

    @staticmethod
    async def create_user(
        db: AsyncSession,
        email: str,
        password: str,
        full_name: str,
        role: UserRole = UserRole.INTERN,
    ) -> User:
        # Check duplicate email
        result = await db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            raise ValueError("Un utilisateur avec cet email existe déjà")

        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=role,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def get_all_users(
        db: AsyncSession,
        role: UserRole | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[User], int]:
        query = select(User)
        count_query = select(func.count()).select_from(User)

        if role:
            query = query.where(User.role == role)
            count_query = count_query.where(User.role == role)

        total = (await db.execute(count_query)).scalar() or 0
        result = await db.execute(
            query.order_by(User.created_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def update_user(
        db: AsyncSession,
        user_id: UUID,
        full_name: str | None = None,
        email: str | None = None,
        is_active: bool | None = None,
    ) -> User:
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            raise ValueError("Utilisateur introuvable")

        if email and email != user.email:
            dup = await db.execute(select(User).where(User.email == email))
            if dup.scalar_one_or_none():
                raise ValueError("Cet email est déjà utilisé")
            user.email = email

        if full_name is not None:
            user.full_name = full_name
        if is_active is not None:
            user.is_active = is_active

        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def deactivate_user(db: AsyncSession, user_id: UUID) -> User:
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            raise ValueError("Utilisateur introuvable")
        user.is_active = False
        await db.commit()
        await db.refresh(user)
        return user