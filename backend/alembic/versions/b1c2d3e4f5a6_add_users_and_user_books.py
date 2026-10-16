"""add users and user_books.

Revision ID: b1c2d3e4f5a6
Revises: f6a7b8c9d0e1
Create Date: 2026-10-16 10:00:00.000000

Introduces per-owner libraries without touching shared book content. Books that
predate ownership are adopted by a single anonymous owner so no book row is left
without a membership.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_OWNER_ID = 'legacy-anonymous'


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=255), nullable=False),
        sa.Column('is_anonymous', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'user_books',
        sa.Column('owner_id', sa.String(length=255), nullable=False),
        sa.Column('book_id', sa.String(length=255), nullable=False),
        sa.Column(
            'added_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('owner_id', 'book_id'),
    )
    op.create_index(
        'ix_user_books_owner_deleted', 'user_books', ['owner_id', 'deleted_at']
    )
    op.execute(
        sa.text(
            'INSERT INTO users (id, is_anonymous, created_at) '
            'VALUES (:owner_id, true, now()) ON CONFLICT (id) DO NOTHING'
        ).bindparams(owner_id=LEGACY_OWNER_ID)
    )
    op.execute(
        sa.text(
            'INSERT INTO user_books (owner_id, book_id, added_at) '
            'SELECT :owner_id, id, now() FROM books '
            'ON CONFLICT (owner_id, book_id) DO NOTHING'
        ).bindparams(owner_id=LEGACY_OWNER_ID)
    )


def downgrade() -> None:
    op.drop_index('ix_user_books_owner_deleted', table_name='user_books')
    op.drop_table('user_books')
    op.drop_table('users')
