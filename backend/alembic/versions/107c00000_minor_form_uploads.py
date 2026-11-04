"""Private minor consent form template and submissions.

Revision ID: 107c00000
Revises: 107b00000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "107c00000"
down_revision = "107b00000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "minor_form_templates",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_table(
        "minor_form_submissions",
        sa.Column("participant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=64), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_digest", sa.String(length=64), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["participants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("participant_id"),
    )
    op.create_index(
        "ix_minor_form_submissions_token_digest",
        "minor_form_submissions",
        ["token_digest"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_minor_form_submissions_token_digest",
        table_name="minor_form_submissions",
    )
    op.drop_table("minor_form_submissions")
    op.drop_table("minor_form_templates")
