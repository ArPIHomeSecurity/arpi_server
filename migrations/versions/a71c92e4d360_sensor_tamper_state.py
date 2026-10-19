"""Add a dedicated sensor tamper state.

Revision ID: a71c92e4d360
Revises: 7bc5e0a14f6d
"""

import sqlalchemy as sa
from alembic import op

revision = "a71c92e4d360"
down_revision = "7bc5e0a14f6d"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sensor",
        sa.Column("tamper", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

def downgrade():
    op.drop_column("sensor", "tamper")
