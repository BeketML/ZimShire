"""add_uq_market_cache_ticker_type

Revision ID: 0f4fa9ae9f1c
Revises: d4e8a1b2c903
Create Date: 2026-05-27 18:09:41.539963

"""
from typing import Sequence, Union

from alembic import op

revision: str = '0f4fa9ae9f1c'
down_revision: Union[str, Sequence[str], None] = 'd4e8a1b2c903'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint('uq_market_cache_ticker_type', 'market_data_cache', ['ticker', 'data_type'])


def downgrade() -> None:
    op.drop_constraint('uq_market_cache_ticker_type', 'market_data_cache', type_='unique')
