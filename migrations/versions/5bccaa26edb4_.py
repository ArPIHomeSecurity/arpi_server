"""empty message

Revision ID: 5bccaa26edb4
Revises: c62c0e73219f
Create Date: 2024-01-10 17:21:24.892651

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5bccaa26edb4'
down_revision = 'c62c0e73219f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('sensor', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ui_hide', sa.Boolean(), nullable=False, server_default="false"))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('sensor', schema=None) as batch_op:
        batch_op.drop_column('ui_hide')

    # ### end Alembic commands ###
