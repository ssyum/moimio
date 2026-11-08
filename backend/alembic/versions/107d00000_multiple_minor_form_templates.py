"""Allow multiple event-specific minor form PDFs.

Revision ID: 107d00000
Revises: 107c00000
"""

from alembic import op
import sqlalchemy as sa


revision = "107d00000"
down_revision = "107c00000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "minor_form_templates_pkey",
        "minor_form_templates",
        type_="primary",
    )
    op.create_primary_key(
        "minor_form_templates_pkey",
        "minor_form_templates",
        ["storage_key"],
    )
    op.create_index(
        "ix_minor_form_templates_event_id",
        "minor_form_templates",
        ["event_id"],
    )


def downgrade() -> None:
    has_multiple_templates = op.get_bind().execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM minor_form_templates "
            "GROUP BY event_id HAVING COUNT(*) > 1"
            ")"
        )
    ).scalar_one()
    if has_multiple_templates:
        raise RuntimeError(
            "Cannot downgrade multiple minor form PDFs to the single-file schema. "
            "Remove extra PDFs for each event first."
        )
    op.drop_index(
        "ix_minor_form_templates_event_id",
        table_name="minor_form_templates",
    )
    op.drop_constraint(
        "minor_form_templates_pkey",
        "minor_form_templates",
        type_="primary",
    )
    op.create_primary_key(
        "minor_form_templates_pkey",
        "minor_form_templates",
        ["event_id"],
    )
