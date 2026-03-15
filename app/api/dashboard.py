"""Router pour le dashboard admin."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import require_admin
from app.models.user import User
from app.schemas.dashboard import DashboardKPIs
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/admin", tags=["Dashboard"])


@router.get("/dashboard", response_model=DashboardKPIs)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Tableau de bord admin : KPIs globaux et par stagiaire."""
    return await DashboardService.get_kpis(db)
