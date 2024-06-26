"""empty message

Revision ID: e72781fbd520
Revises: b525bd3091af
Create Date: 2024-03-24 22:06:32.507341

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e72781fbd520'
down_revision = 'b525bd3091af'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('alert_sensor', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name', sa.String(length=16), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('silent', sa.Boolean(), nullable=True, server_default=None))
        batch_op.add_column(sa.Column('monitor_period', sa.Integer(), nullable=True, server_default=None))
        batch_op.add_column(sa.Column('monitor_threshold', sa.Integer(), nullable=True, server_default='100'))

    with op.batch_alter_table('arm_sensor', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name', sa.String(length=16), nullable=False, server_default=''))

    with op.batch_alter_table('sensor', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name', sa.String(length=16), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('silent_alert', sa.Boolean(), nullable=True, server_default='false'))
        batch_op.add_column(sa.Column('monitor_period', sa.Integer(), nullable=True, server_default=None))
        batch_op.add_column(sa.Column('monitor_threshold', sa.Integer(), nullable=True, server_default='100'))
        batch_op.alter_column('description',
               existing_type=sa.VARCHAR(),
               nullable=True)

    connection = op.get_bind()
    connection.execute(sa.text("UPDATE sensor SET name = substr(description, 1, 16) WHERE name = ''"))
    connection.execute(sa.text("UPDATE alert_sensor SET name = substr(description, 1, 16) WHERE name = ''"))
    connection.execute(sa.text("UPDATE arm_sensor SET name = substr(description, 1, 16) WHERE name = ''"))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('sensor', schema=None) as batch_op:
        batch_op.alter_column('description',
               existing_type=sa.VARCHAR(),
               nullable=False)
        batch_op.drop_column('monitor_threshold')
        batch_op.drop_column('monitor_period')
        batch_op.drop_column('silent_alert')
        batch_op.drop_column('name')

    with op.batch_alter_table('arm_sensor', schema=None) as batch_op:
        batch_op.drop_column('name')

    with op.batch_alter_table('alert_sensor', schema=None) as batch_op:
        batch_op.drop_column('monitor_threshold')
        batch_op.drop_column('monitor_period')
        batch_op.drop_column('silent')
        batch_op.drop_column('name')

    # ### end Alembic commands ###
