"""Allow multiple returned minor consent PDFs per participant.

Revision ID: 107e00000
Revises: 107d00000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "107e00000"
down_revision = "107d00000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "minor_form_submission_files",
        sa.Column("storage_key", sa.String(length=64), nullable=False),
        sa.Column("participant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["participants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("storage_key"),
    )
    op.create_index(
        "ix_minor_form_submission_files_participant_id",
        "minor_form_submission_files",
        ["participant_id"],
    )
    op.execute(
        sa.text(
            "INSERT INTO minor_form_submission_files "
            "(storage_key, participant_id, filename, uploaded_at) "
            "SELECT storage_key, participant_id, filename, uploaded_at "
            "FROM minor_form_submissions WHERE storage_key IS NOT NULL"
        )
    )
    op.drop_column("minor_form_submissions", "storage_key")
    op.drop_column("minor_form_submissions", "filename")
    op.drop_column("minor_form_submissions", "uploaded_at")


def downgrade() -> None:
    has_multiple_files = op.get_bind().execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM minor_form_submission_files "
            "GROUP BY participant_id HAVING COUNT(*) > 1"
            ")"
        )
    ).scalar_one()
    if has_multiple_files:
        raise RuntimeError(
            "Cannot downgrade multiple submitted PDFs to the single-file schema. "
            "Remove extra PDFs for each participant first."
        )
    op.add_column(
        "minor_form_submissions",
        sa.Column("storage_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "minor_form_submissions",
        sa.Column("filename", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "minor_form_submissions",
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE minor_form_submissions AS submission "
            "SET storage_key = submitted_file.storage_key, "
            "filename = submitted_file.filename, "
            "uploaded_at = submitted_file.uploaded_at "
            "FROM minor_form_submission_files AS submitted_file "
            "WHERE submission.participant_id = submitted_file.participant_id"
        )
    )
    op.drop_index(
        "ix_minor_form_submission_files_participant_id",
        table_name="minor_form_submission_files",
    )
    op.drop_table("minor_form_submission_files")
