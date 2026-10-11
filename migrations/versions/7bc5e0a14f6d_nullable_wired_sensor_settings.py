"""Allow Zigbee sensors to omit wired settings.

Revision ID: 7bc5e0a14f6d
Revises: 05f4927ec33b
"""

import sqlalchemy as sa
from alembic import op

revision = "7bc5e0a14f6d"
down_revision = "05f4927ec33b"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("sensor") as batch_op:
        batch_op.alter_column(
            "channel_type",
            existing_type=sa.Enum(
                "basic", "normal", "channel_a", "channel_b", name="channel_types"
            ),
            nullable=True,
            server_default=None,
        )
        batch_op.alter_column(
            "sensor_contact_type",
            existing_type=sa.Enum("NO", "NC", name="sensor_contact_types"),
            nullable=True,
            server_default=None,
        )
        batch_op.alter_column(
            "sensor_eol_count",
            existing_type=sa.Enum("single", "double", name="sensor_eol_count"),
            nullable=True,
            server_default=None,
        )

    op.execute(
        "UPDATE sensor SET channel_type = NULL, sensor_contact_type = NULL, "
        "sensor_eol_count = NULL WHERE zigbee_device_id IS NOT NULL"
    )


def downgrade():
    op.execute(
        "UPDATE sensor SET channel_type = 'normal', sensor_contact_type = 'NC', "
        "sensor_eol_count = 'single' WHERE channel_type IS NULL "
        "OR sensor_contact_type IS NULL OR sensor_eol_count IS NULL"
    )

    with op.batch_alter_table("sensor") as batch_op:
        batch_op.alter_column(
            "channel_type",
            existing_type=sa.Enum(
                "basic", "normal", "channel_a", "channel_b", name="channel_types"
            ),
            nullable=False,
            server_default="normal",
        )
        batch_op.alter_column(
            "sensor_contact_type",
            existing_type=sa.Enum("NO", "NC", name="sensor_contact_types"),
            nullable=False,
            server_default="NC",
        )
        batch_op.alter_column(
            "sensor_eol_count",
            existing_type=sa.Enum("single", "double", name="sensor_eol_count"),
            nullable=False,
            server_default="single",
        )