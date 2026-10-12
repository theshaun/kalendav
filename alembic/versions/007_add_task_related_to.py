"""Add related_to to tasks (VTODO RELATED-TO, RFC 5545 3.8.4.5)

Stores the UID of the parent component this task references (RELTYPE=PARENT,
the relation task apps use for subtasks). Other RELTYPEs stay in raw_ics only.

Revision ID: 007
Revises: 006
Create Date: 2026-10-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('related_to', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'related_to')
