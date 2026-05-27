"""add_user_name_surname

Revision ID: d4e8a1b2c903
Revises: c1a3f9d2e847
Create Date: 2026-05-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e8a1b2c903"
down_revision: Union[str, Sequence[str], None] = "c1a3f9d2e847"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("name", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("surname", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "surname")
    op.drop_column("users", "name")
