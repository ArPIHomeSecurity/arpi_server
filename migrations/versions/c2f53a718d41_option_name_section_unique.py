"""Require unique option name and section pairs.

Revision ID: c2f53a718d41
Revises: a71c92e4d360
"""

from alembic import op

revision = "c2f53a718d41"
down_revision = "a71c92e4d360"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_option_name_section",
        "option",
        ["name", "section"],
    )


def downgrade():
    op.drop_constraint("uq_option_name_section", "option", type_="unique")
