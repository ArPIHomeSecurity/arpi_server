"""Persist IAS Zone device type.

Revision ID: 8d6c1e2f7a90
Revises: 4f5bdd462125
"""

import sqlalchemy as sa
from alembic import op

revision = "8d6c1e2f7a90"
down_revision = "4f5bdd462125"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("zigbee_device", sa.Column("zone_type", sa.Integer(), nullable=True))

    # populate new sensor types
    op.execute(
        "INSERT INTO sensor_type (name, description) VALUES "
        "('Contact', 'IAS Zone contact switch'),"
        "('Fire', 'IAS Zone fire sensor'),"
        "('Water', 'IAS Zone water sensor'),"
        "('CO', 'IAS Zone carbon monoxide sensor'),"
        "('Emergency', 'IAS Zone emergency device'),"
        "('Vibration', 'IAS Zone vibration sensor'),"
        "('Remote', 'IAS Zone remote control'),"
        "('Key fob', 'IAS Zone key fob'),"
        "('Keypad', 'IAS Zone keypad'),"
        "('Warning', 'IAS Zone warning device'),"
        "('Glass', 'IAS Zone glass break sensor'),"
        "('Repeater', 'IAS Zone security repeater')"
    )


def downgrade():
    op.drop_column("zigbee_device", "zone_type")

    # remove the sensor types added in the upgrade
    op.execute(
        "DELETE FROM sensor_type WHERE name IN ("
        "'Contact', 'Fire', 'Water', 'CO', 'Emergency', 'Vibration', "
        "'Remote', 'Key fob', 'Keypad', 'Warning', 'Glass', 'Repeater'"
        ")"
    )
