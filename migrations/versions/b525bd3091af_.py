"""empty message

Revision ID: b525bd3091af
Revises: 
Create Date: 2024-03-14 18:45:58.907046

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b525bd3091af'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('alert',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('silent', sa.Boolean(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('area',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('arm_state', sa.Enum('AWAY', 'STAY', 'MIXED', 'DISARM', name='armstates'), nullable=False),
    sa.Column('deleted', sa.Boolean(), nullable=True),
    sa.Column('ui_order', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('keypad_type',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=True),
    sa.Column('description', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('option',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('section', sa.String(length=32), nullable=False),
    sa.Column('value', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('sensor_type',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=16), nullable=True),
    sa.Column('description', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('user',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('role', sa.String(length=12), nullable=False),
    sa.Column('registration_code', sa.String(length=64), nullable=True),
    sa.Column('registration_expiry', sa.DateTime(timezone=True), nullable=True),
    sa.Column('card_registration_expiry', sa.DateTime(timezone=True), nullable=True),
    sa.Column('access_code', sa.String(length=64), nullable=False),
    sa.Column('fourkey_code', sa.String(length=64), nullable=False),
    sa.Column('comment', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('registration_code')
    )
    op.create_table('zone',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('description', sa.String(), nullable=False),
    sa.Column('disarmed_delay', sa.Integer(), nullable=True),
    sa.Column('away_alert_delay', sa.Integer(), nullable=True),
    sa.Column('stay_alert_delay', sa.Integer(), nullable=True),
    sa.Column('away_arm_delay', sa.Integer(), nullable=True),
    sa.Column('stay_arm_delay', sa.Integer(), nullable=True),
    sa.Column('deleted', sa.Boolean(), nullable=True),
    sa.Column('ui_order', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('card',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=True),
    sa.Column('description', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('keypad',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=True),
    sa.Column('type_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['type_id'], ['keypad_type.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('output',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=16), nullable=True),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('channel', sa.Integer(), nullable=True),
    sa.Column('state', sa.Boolean(), nullable=False),
    sa.Column('trigger_type', sa.Enum('area', 'system', 'button', name='output_trigger_type'), nullable=False),
    sa.Column('area_id', sa.Integer(), nullable=True),
    sa.Column('delay', sa.Integer(), nullable=True),
    sa.Column('duration', sa.Integer(), nullable=False),
    sa.Column('default_state', sa.Boolean(), nullable=True),
    sa.Column('ui_order', sa.Integer(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['area_id'], ['area.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('sensor',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('channel', sa.Integer(), nullable=True),
    sa.Column('reference_value', sa.Float(), nullable=True),
    sa.Column('alert', sa.Boolean(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=True),
    sa.Column('deleted', sa.Boolean(), nullable=True),
    sa.Column('description', sa.String(), nullable=False),
    sa.Column('zone_id', sa.Integer(), nullable=False),
    sa.Column('area_id', sa.Integer(), nullable=False),
    sa.Column('type_id', sa.Integer(), nullable=False),
    sa.Column('ui_order', sa.Integer(), nullable=True),
    sa.Column('ui_hidden', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['area_id'], ['area.id'], ),
    sa.ForeignKeyConstraint(['type_id'], ['sensor_type.id'], ),
    sa.ForeignKeyConstraint(['zone_id'], ['zone.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('alert_sensor',
    sa.Column('alert_id', sa.Integer(), nullable=False),
    sa.Column('sensor_id', sa.Integer(), nullable=False),
    sa.Column('channel', sa.Integer(), nullable=True),
    sa.Column('type_id', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delay', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['alert_id'], ['alert.id'], ),
    sa.ForeignKeyConstraint(['sensor_id'], ['sensor.id'], ),
    sa.ForeignKeyConstraint(['type_id'], ['sensor_type.id'], ),
    sa.PrimaryKeyConstraint('alert_id', 'sensor_id')
    )
    op.create_table('arm',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('type', sa.Enum('AWAY', 'STAY', 'MIXED', 'DISARM', name='armstates'), nullable=False),
    sa.Column('time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('keypad_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('alert_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['alert_id'], ['alert.id'], ),
    sa.ForeignKeyConstraint(['keypad_id'], ['keypad.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('arm_sensor',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('arm_id', sa.Integer(), nullable=True),
    sa.Column('sensor_id', sa.Integer(), nullable=True),
    sa.Column('channel', sa.Integer(), nullable=False),
    sa.Column('type_id', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delay', sa.Integer(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['arm_id'], ['arm.id'], ),
    sa.ForeignKeyConstraint(['sensor_id'], ['sensor.id'], ),
    sa.ForeignKeyConstraint(['type_id'], ['sensor_type.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('disarm',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('keypad_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('alert_id', sa.Integer(), nullable=True),
    sa.Column('arm_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['alert_id'], ['alert.id'], ),
    sa.ForeignKeyConstraint(['arm_id'], ['arm.id'], ),
    sa.ForeignKeyConstraint(['keypad_id'], ['keypad.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('disarm')
    op.drop_table('arm_sensor')
    op.drop_table('arm')
    op.drop_table('alert_sensor')
    op.drop_table('sensor')
    op.drop_table('output')
    op.drop_table('keypad')
    op.drop_table('card')
    op.drop_table('zone')
    op.drop_table('user')
    op.drop_table('sensor_type')
    op.drop_table('option')
    op.drop_table('keypad_type')
    op.drop_table('area')
    op.drop_table('alert')
    # ### end Alembic commands ###
