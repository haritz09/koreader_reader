"""add knowledge tables.

Revision ID: a1b2c3d4e5f6
Revises: 150455de119a
Create Date: 2026-09-29 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '150455de119a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('entities',
    sa.Column('id', sa.String(length=255), nullable=False),
    sa.Column('book_id', sa.String(length=255), nullable=False),
    sa.Column('chunk_id', sa.String(length=255), nullable=False),
    sa.Column('name', sa.String(length=500), nullable=False),
    sa.Column('entity_type', sa.String(length=100), nullable=False),
    sa.Column('reading_position', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['book_id'], ['books.id']),
    sa.ForeignKeyConstraint(['chunk_id'], ['chunks.id']),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.create_index('ix_entities_book_reading_position', ['book_id', 'reading_position'])

    op.create_table('facts',
    sa.Column('id', sa.String(length=255), nullable=False),
    sa.Column('book_id', sa.String(length=255), nullable=False),
    sa.Column('chunk_id', sa.String(length=255), nullable=False),
    sa.Column('statement', sa.Text(), nullable=False),
    sa.Column('subject', sa.String(length=500), nullable=True),
    sa.Column('object', sa.String(length=500), nullable=True),
    sa.Column('reading_position', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['book_id'], ['books.id']),
    sa.ForeignKeyConstraint(['chunk_id'], ['chunks.id']),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('facts', schema=None) as batch_op:
        batch_op.create_index('ix_facts_book_reading_position', ['book_id', 'reading_position'])

    op.create_table('events',
    sa.Column('id', sa.String(length=255), nullable=False),
    sa.Column('book_id', sa.String(length=255), nullable=False),
    sa.Column('chunk_id', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('reading_position', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['book_id'], ['books.id']),
    sa.ForeignKeyConstraint(['chunk_id'], ['chunks.id']),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.create_index('ix_events_book_reading_position', ['book_id', 'reading_position'])

    op.create_table('locations',
    sa.Column('id', sa.String(length=255), nullable=False),
    sa.Column('book_id', sa.String(length=255), nullable=False),
    sa.Column('chunk_id', sa.String(length=255), nullable=False),
    sa.Column('name', sa.String(length=500), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('reading_position', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['book_id'], ['books.id']),
    sa.ForeignKeyConstraint(['chunk_id'], ['chunks.id']),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.create_index('ix_locations_book_reading_position', ['book_id', 'reading_position'])


def downgrade() -> None:
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.drop_index('ix_locations_book_reading_position')
    op.drop_table('locations')

    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_index('ix_events_book_reading_position')
    op.drop_table('events')

    with op.batch_alter_table('facts', schema=None) as batch_op:
        batch_op.drop_index('ix_facts_book_reading_position')
    op.drop_table('facts')

    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.drop_index('ix_entities_book_reading_position')
    op.drop_table('entities')
