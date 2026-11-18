"""add chunk extraction state.

Revision ID: b2c3d4e5f6a7
Revises: a7b8c9d0e1f2
Create Date: 2026-11-17 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'chunks',
        sa.Column('extracted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE chunks SET extracted_at = now()
        WHERE EXISTS (SELECT 1 FROM entities WHERE entities.chunk_id = chunks.id)
           OR EXISTS (SELECT 1 FROM facts WHERE facts.chunk_id = chunks.id)
           OR EXISTS (SELECT 1 FROM events WHERE events.chunk_id = chunks.id)
           OR EXISTS (SELECT 1 FROM locations WHERE locations.chunk_id = chunks.id)
        """
    )


def downgrade() -> None:
    op.drop_column('chunks', 'extracted_at')
