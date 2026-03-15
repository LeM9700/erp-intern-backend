"""add TASK_COMMENT to activityaction enum

Revision ID: 005
Revises: 004
Create Date: 2026-03-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: str = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("COMMIT"))
    connection.execute(
        sa.text("ALTER TYPE activityaction ADD VALUE IF NOT EXISTS 'TASK_COMMENT'")
    )


def downgrade() -> None:
    # PostgreSQL ne supporte pas la suppression d'une valeur d'enum
    pass
