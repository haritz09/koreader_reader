"""add book lookup indexes for chapters and community runs.

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-11-18 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_chapters_book_id', 'chapters', ['book_id'])
    op.create_index(
        'ix_rag_community_runs_book_id', 'rag_community_runs', ['book_id']
    )


def downgrade() -> None:
    op.drop_index('ix_rag_community_runs_book_id', table_name='rag_community_runs')
    op.drop_index('ix_chapters_book_id', table_name='chapters')
