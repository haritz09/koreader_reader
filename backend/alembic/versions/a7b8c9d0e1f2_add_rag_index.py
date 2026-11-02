"""add graphrag embeddings and hierarchical communities.

Revision ID: a7b8c9d0e1f2
Revises: d1e2f3a4b5c6
Create Date: 2026-11-02 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_READING_POSITION = 'reading_position >= 0.0 AND reading_position <= 1.0'
_SOURCE_TYPE_VALUES = "'chunk', 'entity', 'fact', 'event', 'location'"
_STATUS_VALUES = "'pending', 'building', 'ready', 'partial', 'failed'"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        'rag_embeddings',
        sa.Column('id', sa.String(length=255), nullable=False),
        sa.Column('book_id', sa.String(length=255), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('source_id', sa.String(length=255), nullable=False),
        sa.Column('chunk_id', sa.String(length=255), nullable=True),
        sa.Column('reading_position', sa.Float(), nullable=False),
        sa.Column('model', sa.String(length=128), nullable=False),
        sa.Column('dimensions', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('embedding', Vector(768), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chunk_id'], ['chunks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_type', 'source_id', 'model'),
        sa.CheckConstraint(_READING_POSITION, name='ck_rag_embeddings_reading_position'),
        sa.CheckConstraint(
            f'source_type IN ({_SOURCE_TYPE_VALUES})',
            name='ck_rag_embeddings_source_type',
        ),
    )
    op.create_index(
        'ix_rag_embeddings_book_source_position',
        'rag_embeddings',
        ['book_id', 'source_type', 'reading_position'],
    )
    op.create_index(
        'ix_rag_embeddings_book_model',
        'rag_embeddings',
        ['book_id', 'model'],
    )

    op.create_table(
        'rag_community_runs',
        sa.Column('id', sa.String(length=255), nullable=False),
        sa.Column('book_id', sa.String(length=255), nullable=False),
        sa.Column('graph_revision', sa.Integer(), nullable=False),
        sa.Column('algorithm', sa.String(length=64), nullable=False),
        sa.Column('parameters', JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('node_count', sa.Integer(), nullable=False),
        sa.Column('edge_count', sa.Integer(), nullable=False),
        sa.Column('modularity', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'rag_communities',
        sa.Column('id', sa.String(length=255), nullable=False),
        sa.Column('run_id', sa.String(length=255), nullable=False),
        sa.Column('book_id', sa.String(length=255), nullable=False),
        sa.Column('parent_id', sa.String(length=255), nullable=True),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('seed_node_id', sa.String(length=255), nullable=False),
        sa.Column('signature_hash', sa.String(length=64), nullable=False),
        sa.Column('first_seen_position', sa.Float(), nullable=False),
        sa.Column('member_count', sa.Integer(), nullable=False),
        sa.Column('internal_weight', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['rag_community_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_id'], ['rag_communities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(_READING_POSITION, name='ck_rag_communities_reading_position'),
    )
    op.create_index('ix_rag_communities_run_level', 'rag_communities', ['run_id', 'level'])
    op.create_index('ix_rag_communities_book_level', 'rag_communities', ['book_id', 'level'])

    op.create_table(
        'rag_community_members',
        sa.Column('community_id', sa.String(length=255), nullable=False),
        sa.Column('node_id', sa.String(length=255), nullable=False),
        sa.Column('node_type', sa.String(length=32), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ['community_id'], ['rag_communities.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('community_id', 'node_id'),
    )
    op.create_index('ix_rag_community_members_node', 'rag_community_members', ['node_id'])

    op.create_table(
        'rag_index_states',
        sa.Column('book_id', sa.String(length=255), nullable=False),
        sa.Column('rag_revision', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('graph_revision', sa.Integer(), server_default='0', nullable=False),
        sa.Column('current_run_id', sa.String(length=255), nullable=True),
        sa.Column('embedding_model', sa.String(length=128), server_default='', nullable=False),
        sa.Column('error', sa.String(length=2000), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['current_run_id'], ['rag_community_runs.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('book_id'),
        sa.CheckConstraint(
            f'status IN ({_STATUS_VALUES})',
            name='ck_rag_index_states_status',
        ),
    )


def downgrade() -> None:
    op.drop_table('rag_index_states')
    op.drop_index('ix_rag_community_members_node', table_name='rag_community_members')
    op.drop_table('rag_community_members')
    op.drop_index('ix_rag_communities_book_level', table_name='rag_communities')
    op.drop_index('ix_rag_communities_run_level', table_name='rag_communities')
    op.drop_table('rag_communities')
    op.drop_table('rag_community_runs')
    op.drop_index('ix_rag_embeddings_book_model', table_name='rag_embeddings')
    op.drop_index('ix_rag_embeddings_book_source_position', table_name='rag_embeddings')
    op.drop_table('rag_embeddings')
