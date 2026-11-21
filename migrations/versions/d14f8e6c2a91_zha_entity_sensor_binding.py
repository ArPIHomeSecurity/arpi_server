"""Use ZHA entity IDs for Zigbee sensor bindings.

Revision ID: d14f8e6c2a91
Revises: a98b022535a1
"""

import sqlalchemy as sa
from alembic import op

revision = "d14f8e6c2a91"
down_revision = "a98b022535a1"
branch_labels = None
depends_on = None


def _convert_device_metadata(ieee_address: str, metadata):
    if not isinstance(metadata, dict):
        return metadata

    metadata = {**metadata}
    signals = metadata.pop("signals", None) or []
    metadata.pop("capabilities", None)
    entities = list(metadata.get("entities") or [])
    known_entity_ids = {
        entity.get("entityId") for entity in entities if isinstance(entity, dict)
    }
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        endpoint = signal.get("endpoint")
        cluster_id = signal.get("clusterId")
        if endpoint is None or cluster_id is None:
            continue
        unique_id = f"{ieee_address.lower()}-{endpoint}-{cluster_id}"
        entity_id = f"binary_sensor/{unique_id}"
        if entity_id in known_entity_ids:
            continue
        entities.append(
            {
                "entityId": entity_id,
                "uniqueId": unique_id,
                "platform": "binary_sensor",
                "name": signal.get("field")
                or signal.get("attribute")
                or signal.get("cluster")
                or entity_id,
                "cluster": signal.get("cluster"),
                "attribute": signal.get("attribute"),
                "deviceClass": None,
                "value": False,
                "available": True,
                "attributes": {},
            }
        )
        known_entity_ids.add(entity_id)
    if entities:
        metadata["entities"] = entities
    return metadata


def upgrade():
    op.add_column("sensor", sa.Column("zigbee_entity_id", sa.String(length=512), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT sensor.id, zigbee_device.ieee_address, sensor.zigbee_endpoint,
                   sensor.zigbee_cluster_id
            FROM sensor
            JOIN zigbee_device ON zigbee_device.id = sensor.zigbee_device_id
            WHERE sensor.zigbee_device_id IS NOT NULL
              AND sensor.zigbee_endpoint IS NOT NULL
              AND sensor.zigbee_cluster_id IS NOT NULL
            """
        )
    ).mappings().all()
    for row in rows:
        unique_id = (
            f"{row['ieee_address'].lower()}-{row['zigbee_endpoint']}-{row['zigbee_cluster_id']}"
        )
        connection.execute(
            sa.text("UPDATE sensor SET zigbee_entity_id = :entity_id WHERE id = :id"),
            {"entity_id": f"binary_sensor/{unique_id}", "id": row["id"]},
        )

    zigbee_device = sa.table(
        "zigbee_device",
        sa.column("id", sa.Integer),
        sa.column("ieee_address", sa.String),
        sa.column("metadata", sa.JSON),
    )
    devices = connection.execute(
        sa.select(
            zigbee_device.c.id,
            zigbee_device.c.ieee_address,
            zigbee_device.c.metadata,
        )
    ).mappings().all()
    for device in devices:
        metadata = _convert_device_metadata(device["ieee_address"], device["metadata"])
        if metadata != device["metadata"]:
            connection.execute(
                zigbee_device.update()
                .where(zigbee_device.c.id == device["id"])
                .values(metadata=metadata)
            )

    with op.batch_alter_table("sensor") as batch_op:
        batch_op.drop_column("zigbee_endpoint")
        batch_op.drop_column("zigbee_cluster_id")
        batch_op.drop_column("zigbee_attribute_id")
        batch_op.drop_column("zigbee_field")


def downgrade():
    with op.batch_alter_table("sensor") as batch_op:
        batch_op.add_column(sa.Column("zigbee_endpoint", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("zigbee_cluster_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("zigbee_attribute_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("zigbee_field", sa.String(length=32), nullable=True))
        batch_op.drop_column("zigbee_entity_id")
