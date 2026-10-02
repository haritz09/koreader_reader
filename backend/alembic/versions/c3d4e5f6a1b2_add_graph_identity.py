"""add graph identity and reading position constraints.

Revision ID: c3d4e5f6a1b2
Revises: a1b2c3d4e5f6
Create Date: 2026-09-30 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a1b2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_READING_POSITION = 'reading_position >= 0.0 AND reading_position <= 1.0'


def upgrade() -> None:
    op.add_column('books', sa.Column('graph_revision', sa.Integer(), nullable=False, server_default='0'))

    op.add_column('entities', sa.Column('canonical_id', sa.String(length=255), nullable=True))
    op.add_column('entities', sa.Column('resolution_method', sa.String(length=32), nullable=True))
    op.create_foreign_key(
        'fk_entities_canonical_id',
        'entities',
        'entities',
        ['canonical_id'],
        ['id'],
    )
    op.create_index('ix_entities_book_canonical_id', 'entities', ['book_id', 'canonical_id'])

    # Existing rows are their own canonical entity until resolution runs.
    op.execute('UPDATE entities SET canonical_id = id WHERE canonical_id IS NULL')

    op.create_check_constraint('ck_books_progress_position', 'books', 'progress_position >= 0.0 AND progress_position <= 1.0')
    op.create_check_constraint('ck_entities_reading_position', 'entities', _READING_POSITION)
    op.create_check_constraint('ck_facts_reading_position', 'facts', _READING_POSITION)
    op.create_check_constraint('ck_events_reading_position', 'events', _READING_POSITION)
    op.create_check_constraint('ck_locations_reading_position', 'locations', _READING_POSITION)


def downgrade() -> None:
    op.drop_constraint('ck_locations_reading_position', 'locations', type_='check')
    op.drop_constraint('ck_events_reading_position', 'events', type_='check')
    op.drop_constraint('ck_facts_reading_position', 'facts', type_='check')
    op.drop_constraint('ck_entities_reading_position', 'entities', type_='check')
    op.drop_constraint('ck_books_progress_position', 'books', type_='check')

    op.drop_index('ix_entities_book_canonical_id', table_name='entities')
    op.drop_constraint('fk_entities_canonical_id', 'entities', type_='foreignkey')
    op.drop_column('entities', 'resolution_method')
    op.drop_column('entities', 'canonical_id')

    op.drop_column('books', 'graph_revision')
