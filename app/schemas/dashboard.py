"""Schémas pour le dashboard admin."""
from pydantic import BaseModel
from uuid import UUID


class InternSummary(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    hours_this_week: float
    hours_this_month: float
    is_currently_clocked_in: bool
    tasks_pending: int
    tasks_in_progress: int
    tasks_submitted: int
    tasks_approved: int
    tasks_rejected: int


class DashboardKPIs(BaseModel):
    """KPIs globaux du tableau de bord admin."""
    total_interns: int
    active_interns: int
    live_sessions_count: int
    total_hours_this_week: float
    total_hours_this_month: float
    tasks_pending: int
    tasks_in_progress: int
    tasks_submitted: int
    tasks_approved: int
    tasks_rejected: int
    interns: list[InternSummary]
