from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('books', sa.Column('title', sa.String(length=512), nullable=True))
    op.add_column('books', sa.Column('author', sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column('books', 'author')
    op.drop_column('books', 'title')
