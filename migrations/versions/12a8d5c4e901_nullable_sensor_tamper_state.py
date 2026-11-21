"""Make sensor tamper state nullable when detection is unavailable.

Revision ID: 12a8d5c4e901
Revises: d14f8e6c2a91
"""

import sqlalchemy as sa
from alembic import op

revision = "12a8d5c4e901"
down_revision = "d14f8e6c2a91"
branch_labels = None
depends_on = None


def _supports_zigbee_tamper(metadata, entity_id):
    if not isinstance(metadata, dict):
        return False
    return any(
        entity.get("entityId") == entity_id
        and entity.get("cluster") == "IAS Zone"
        and entity.get("attribute") == "zone_status"
        for entity in metadata.get("entities") or []
        if isinstance(entity, dict)
    )


def upgrade():
    with op.batch_alter_table("sensor") as batch_op:
        batch_op.alter_column(
            "tamper",
            existing_type=sa.Boolean(),
            nullable=True,
            server_default=None,
        )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT sensor.id, sensor.channel, sensor.channel_type,
                   sensor.sensor_eol_count, sensor.zigbee_entity_id,
                   zigbee_device.metadata
            FROM sensor
            LEFT JOIN zigbee_device
              ON zigbee_device.id = sensor.zigbee_device_id
            """
        )
    ).mappings().all()

    for row in rows:
        supported = (
            row["channel"] is not None
            and row["channel"] >= 0
            and row["channel_type"] == "normal"
            and row["sensor_eol_count"] == "double"
        ) or _supports_zigbee_tamper(row["metadata"], row["zigbee_entity_id"])
        if not supported:
            connection.execute(
                sa.text("UPDATE sensor SET tamper = NULL WHERE id = :id"),
                {"id": row["id"]},
            )


def downgrade():
    op.execute(sa.text("UPDATE sensor SET tamper = false WHERE tamper IS NULL"))
    with op.batch_alter_table("sensor") as batch_op:
        batch_op.alter_column(
            "tamper",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        )
