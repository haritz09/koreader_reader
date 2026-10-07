"""add importance column to entities.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a1b2c3
Create Date: 2026-10-07 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ENTITY_TYPE_VALUES = "'character', 'enemy', 'artifact', 'organization', 'concept', 'other'"
_ENTITY_TYPE_CHECK = f"entity_type IN ({_ENTITY_TYPE_VALUES})"


def upgrade() -> None:
    op.add_column('entities', sa.Column('importance', sa.Integer(), nullable=True))
    op.create_check_constraint(
        'ck_entities_importance',
        'entities',
        f'importance IS NULL OR importance IN (1, 2, 3)',
    )
    op.drop_constraint('ck_entities_entity_type', 'entities', type_='check')
    op.create_check_constraint('ck_entities_entity_type', 'entities', _ENTITY_TYPE_CHECK)


def downgrade() -> None:
    op.drop_constraint('ck_entities_importance', 'entities', type_='check')
    op.drop_column('entities', 'importance')
