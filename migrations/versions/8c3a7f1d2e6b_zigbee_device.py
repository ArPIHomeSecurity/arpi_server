"""Add registered Zigbee devices.

Revision ID: 8c3a7f1d2e6b
Revises: 710d6b5f7f5b
"""

import sqlalchemy as sa
from alembic import op


revision = "8c3a7f1d2e6b"
down_revision = "710d6b5f7f5b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "zigbee_device",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ieee_address", sa.String(length=23), nullable=False),
        sa.Column("network_address", sa.Integer(), nullable=True),
        sa.Column("manufacturer", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=True),
        sa.Column("availability", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("battery_level", sa.Integer(), nullable=True),
        sa.Column("signal_quality", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ieee_address"),
    )


def downgrade():
    op.drop_table("zigbee_device")
