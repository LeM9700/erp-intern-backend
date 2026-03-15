"""fix files columns rename

Revision ID: 003
Revises: 002
Create Date: 2026-03-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: str = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Renommer les colonnes existantes
    op.alter_column("files", "original_name", new_column_name="original_filename")
    op.alter_column("files", "content_type", new_column_name="mime_type")
    op.alter_column("files", "s3_key", new_column_name="stored_path")

    # Remplacer status (String) par confirmed (Boolean)
    op.add_column(
        "files",
        sa.Column("confirmed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.drop_column("files", "status")


def downgrade() -> None:
    op.add_column(
        "files",
        sa.Column("status", sa.String(), server_default=sa.text("'PENDING'"), nullable=False),
    )
    op.drop_column("files", "confirmed")
    op.alter_column("files", "stored_path", new_column_name="s3_key")
    op.alter_column("files", "mime_type", new_column_name="content_type")
    op.alter_column("files", "original_filename", new_column_name="original_name")