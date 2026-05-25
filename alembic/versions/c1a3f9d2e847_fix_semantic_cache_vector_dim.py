"""keep semantic_cache vector dim at 1536 (text-embedding-3-small)

Revision ID: c1a3f9d2e847
Revises: ba8ef0756cef
Create Date: 2026-05-25 11:32:00.000000

"""
from typing import Sequence, Union

import pgvector.sqlalchemy
from alembic import op

revision: str = "c1a3f9d2e847"
down_revision: Union[str, Sequence[str], None] = "ba8ef0756cef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "semantic_cache",
        "query_embedding",
        type_=pgvector.sqlalchemy.Vector(1536),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "semantic_cache",
        "query_embedding",
        type_=pgvector.sqlalchemy.Vector(1536),
        nullable=False,
    )
