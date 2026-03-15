"""task_proofs: file_id nullable + add proof_url

Revision ID: 004
Revises: 003
Create Date: 2026-03-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "004"
down_revision: str = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make file_id nullable on task_proofs
    op.alter_column(
        "task_proofs",
        "file_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
    )
    # Add proof_url column
    op.add_column(
        "task_proofs",
        sa.Column("proof_url", sa.String(2048), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("task_proofs", "proof_url")
    op.alter_column(
        "task_proofs",
        "file_id",
        existing_type=UUID(as_uuid=True),
        nullable=False,
    )
