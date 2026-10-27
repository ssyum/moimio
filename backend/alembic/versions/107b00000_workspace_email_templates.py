"""Workspace-wide editable transactional email copy.

Revision ID: 107b00000
Revises: 107a00000
Create Date: 2026-10-27
"""

from alembic import op
import sqlalchemy as sa


revision = "107b00000"
down_revision = "107a00000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_settings",
        sa.Column("email_templates", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspace_settings", "email_templates")
