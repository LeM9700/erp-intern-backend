from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import require_admin
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate, UserOut, UserListOut
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Créer un stagiaire (ou admin). Réservé aux admins."""
    try:
        user = await UserService.create_user(
            db=db,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            role=payload.role,
        )
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("", response_model=UserListOut)
async def list_users(
    role: UserRole | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Lister tous les utilisateurs. Réservé aux admins."""
    users, total = await UserService.get_all_users(db, role=role, skip=skip, limit=limit)
    return UserListOut(users=users, total=total)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Détail d'un utilisateur. Réservé aux admins."""
    user = await UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Modifier un utilisateur. Réservé aux admins."""
    try:
        user = await UserService.update_user(
            db=db,
            user_id=user_id,
            full_name=payload.full_name,
            email=payload.email,
            is_active=payload.is_active,
        )
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{user_id}", response_model=UserOut)
async def deactivate_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Désactiver un utilisateur. Réservé aux admins."""
    try:
        user = await UserService.deactivate_user(db, user_id)
        return user
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))