"""Store Zigbee sensor bindings as structured attribute identities.

Revision ID: 9a7c4e1b2d60
Revises: 8d6c1e2f7a90
"""

import sqlalchemy as sa
from alembic import op

revision = "9a7c4e1b2d60"
down_revision = "8d6c1e2f7a90"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sensor", sa.Column("zigbee_cluster_id", sa.Integer(), nullable=True))
    op.add_column("sensor", sa.Column("zigbee_attribute_id", sa.Integer(), nullable=True))
    op.add_column("sensor", sa.Column("zigbee_field", sa.String(length=32), nullable=True))

    with op.batch_alter_table("sensor") as batch_op:
        batch_op.drop_column("zigbee_capability")


def downgrade():
    op.add_column("sensor", sa.Column("zigbee_capability", sa.String(length=32), nullable=True))

    with op.batch_alter_table("sensor") as batch_op:
        batch_op.drop_column("zigbee_field")
        batch_op.drop_column("zigbee_attribute_id")
        batch_op.drop_column("zigbee_cluster_id")
