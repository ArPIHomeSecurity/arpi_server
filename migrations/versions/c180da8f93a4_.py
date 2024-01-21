"""empty message

Revision ID: c180da8f93a4
Revises: dee8e993625e
Create Date: 2024-01-14 11:10:34.401164

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c180da8f93a4'
down_revision = 'dee8e993625e'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('zone', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ui_order', sa.Integer(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('zone', schema=None) as batch_op:
        batch_op.drop_column('ui_order')

    # ### end Alembic commands ###
