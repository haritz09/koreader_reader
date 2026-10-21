"""move reading progress to user_books.

Revision ID: c9d0e1f2a3b4
Revises: b1c2d3e4f5a6
Create Date: 2026-10-21 10:00:00.000000

Reading progress belongs to the reader, not to the shared book. The old
book-level value is copied into every membership before the column is dropped,
so the boundary fails closed: no code can read a position that one owner shares
with another.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user_books',
        sa.Column(
            'progress_position',
            sa.Float(),
            nullable=False,
            server_default='0.0',
        ),
    )
    op.add_column(
        'user_books',
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        'ck_user_books_progress_position',
        'user_books',
        'progress_position >= 0.0 AND progress_position <= 1.0',
    )
    op.execute(
        'UPDATE user_books AS ub SET progress_position = b.progress_position '
        'FROM books AS b WHERE b.id = ub.book_id'
    )
    op.drop_column('books', 'progress_position')


def downgrade() -> None:
    op.add_column(
        'books',
        sa.Column(
            'progress_position',
            sa.Float(),
            nullable=False,
            server_default='0.0',
        ),
    )
    op.execute(
        'UPDATE books AS b SET progress_position = COALESCE(('
        'SELECT MAX(ub.progress_position) FROM user_books AS ub '
        'WHERE ub.book_id = b.id), 0.0)'
    )
    op.create_check_constraint(
        'ck_books_progress_position',
        'books',
        'progress_position >= 0.0 AND progress_position <= 1.0',
    )
    op.alter_column('books', 'progress_position', server_default=None)
    op.drop_constraint(
        'ck_user_books_progress_position', 'user_books', type_='check'
    )
    op.drop_column('user_books', 'last_synced_at')
    op.drop_column('user_books', 'progress_position')
