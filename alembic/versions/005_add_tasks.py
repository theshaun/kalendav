"""Add tasks table for VTODO (CalDAV todo) support

Stores RFC 5545 VTODO components alongside events, scoped per calendar with
the same (calendar_id, uid) uniqueness contract the events table uses. The
DTSTART column is intentionally NOT replicated here — VTODO start dates stay
inside raw_ics; this table only indexes the fields the web UI and CalDAV
REPORT filters need (status, priority, due, completed, percent_complete,
sort_order).

Revision ID: 005
Revises: 004
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('calendar_id', sa.Integer(), nullable=False),
        sa.Column('uid', sa.String(255), nullable=False),
        sa.Column('summary', sa.String(500), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(16), nullable=False, server_default='NEEDS-ACTION'),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('due', sa.DateTime(), nullable=True),
        sa.Column('completed', sa.DateTime(), nullable=True),
        sa.Column('percent_complete', sa.Integer(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('raw_ics', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['calendar_id'], ['calendars.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tasks_calendar_id', 'tasks', ['calendar_id'])
    op.create_index('ix_tasks_uid', 'tasks', ['uid'])
    op.create_index('ix_tasks_calendar_uid', 'tasks', ['calendar_id', 'uid'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_tasks_calendar_uid', table_name='tasks')
    op.drop_index('ix_tasks_uid', table_name='tasks')
    op.drop_index('ix_tasks_calendar_id', table_name='tasks')
    op.drop_table('tasks')
