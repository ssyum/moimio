"""Add a paid registration status.

Revision ID: 107f00000
Revises: 107e00000
"""

from alembic import op


revision = "107f00000"
down_revision = "107e00000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE registration_status ADD VALUE IF NOT EXISTS 'paid'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE participants SET registration_status = 'confirmed' "
        "WHERE registration_status = 'paid'"
    )
    op.execute("ALTER TYPE registration_status RENAME TO registration_status_old")
    op.execute(
        "CREATE TYPE registration_status AS ENUM "
        "('pending', 'confirmed', 'cancelled')"
    )
    op.execute(
        "ALTER TABLE participants ALTER COLUMN registration_status "
        "TYPE registration_status USING registration_status::text::registration_status"
    )
    op.execute("DROP TYPE registration_status_old")
