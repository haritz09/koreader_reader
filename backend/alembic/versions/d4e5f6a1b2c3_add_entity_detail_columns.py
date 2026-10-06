"""add entity description, sub type, aliases and event name.

Revision ID: d4e5f6a1b2c3
Revises: c3d4e5f6a1b2
Create Date: 2026-10-06 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a1b2c3'
down_revision: Union[str, None] = 'c3d4e5f6a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ENTITY_TYPE_VALUES = "'character', 'enemy', 'artifact', 'organization', 'concept', 'other'"

_NORMALIZE_ENTITY_TYPE = """
    UPDATE entities SET entity_type = lower(btrim(entity_type));

    UPDATE entities SET entity_type = CASE
        WHEN entity_type IN ('character', 'enemy', 'artifact', 'organization', 'concept', 'other')
            THEN entity_type
        WHEN entity_type IN (
            'person', 'people', 'protagonist', 'hero', 'main character'
        ) THEN 'character'
        WHEN entity_type IN ('villain', 'antagonist', 'foe') THEN 'enemy'
        WHEN entity_type IN ('item', 'object', 'weapon', 'relic', 'prop') THEN 'artifact'
        WHEN entity_type IN (
            'organisation', 'faction', 'group', 'order', 'institution', 'clan', 'team'
        ) THEN 'organization'
        WHEN entity_type IN (
            'idea', 'knowledge', 'ability', 'magic', 'power', 'lore', 'system'
        ) THEN 'concept'
        ELSE 'other'
    END;
"""

_MOVE_PLACES = """
    UPDATE entities child
    SET canonical_id = child.id
    FROM entities parent
    WHERE child.canonical_id = parent.id
      AND lower(btrim(parent.entity_type)) IN ('place', 'location', 'setting');

    INSERT INTO locations (id, book_id, chunk_id, name, description, reading_position)
    SELECT 'migrated-' || e.id, e.book_id, e.chunk_id, e.name, NULL, e.reading_position
    FROM entities e
    WHERE lower(btrim(e.entity_type)) IN ('place', 'location', 'setting')
    ON CONFLICT DO NOTHING;

    DELETE FROM entities e
    WHERE lower(btrim(e.entity_type)) IN ('place', 'location', 'setting');
"""

_BACKFILL_EVENT_NAMES = """
    UPDATE events SET name = left(description, 120)
    WHERE btrim(name) = '';
"""


def upgrade() -> None:
    op.add_column('entities', sa.Column('description', sa.Text(), nullable=False, server_default=''))
    op.add_column('entities', sa.Column('sub_type', sa.String(length=100), nullable=True))
    op.add_column('entities', sa.Column('aliases', sa.ARRAY(sa.String(length=500)), nullable=False, server_default='{}'))

    op.add_column('events', sa.Column('name', sa.String(length=500), nullable=False, server_default=''))

    op.execute(_MOVE_PLACES)
    op.execute(_NORMALIZE_ENTITY_TYPE)
    op.execute(_BACKFILL_EVENT_NAMES)

    op.create_check_constraint('ck_entities_entity_type', 'entities', f'entity_type IN ({_ENTITY_TYPE_VALUES})')


def downgrade() -> None:
    op.drop_constraint('ck_entities_entity_type', 'entities', type_='check')

    op.execute(
        """
        INSERT INTO entities (id, book_id, chunk_id, name, entity_type, reading_position)
        SELECT substring(l.id from 10), l.book_id, l.chunk_id, l.name, 'place', l.reading_position
        FROM locations l
        WHERE l.id LIKE 'migrated-%';
        """
    )
    op.execute("DELETE FROM locations WHERE id LIKE 'migrated-%'")

    op.drop_column('events', 'name')
    op.drop_column('entities', 'aliases')
    op.drop_column('entities', 'sub_type')
    op.drop_column('entities', 'description')
