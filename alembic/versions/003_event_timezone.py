"""Add timezone column to events table

Stores the IANA timezone the event was authored in (e.g. "Australia/Brisbane"),
so ICS exports can emit per-event TZID parameters instead of a single global
default. Nullable: existing rows get NULL and fall back to
settings.default_timezone at serialization time.

Revision ID: 003
Revises: 002
Create Date: 2026-07-01

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('events', sa.Column('timezone', sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column('events', 'timezone')
