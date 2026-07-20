"""Backfill events.timezone from DEFAULT_TIMEZONE

Pre-fix state: events.timezone was NULL for every row because the web form
never sent a `tz` field, so create_event stored NULL. The ICS feed and web
endpoint fell back to settings.default_timezone at render time, which papered
over the gap but made per-event tz impossible.

This migration makes the implicit fallback explicit: every NULL row gets
settings.default_timezone (read from the env at migration time). dtstart /
dtend values are NOT shifted — they were already being interpreted as UTC by
the rest of the stack, and that interpretation is preserved.

Revision ID: 004
Revises: 003
Create Date: 2026-07-21

"""
import os
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    default_tz = os.environ.get("DEFAULT_TIMEZONE", "UTC") or "UTC"
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE events SET timezone = :tz WHERE timezone IS NULL"
        ),
        {"tz": default_tz},
    )


def downgrade() -> None:
    # No safe downgrade — we cannot recover which rows were originally NULL.
    # Restoring pre-migration state requires restoring the database from backup.
    pass
