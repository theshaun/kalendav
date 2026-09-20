"""Normalize all-day event storage and heal stale raw_ics

Pre-fix state (three defects surfacing in Outlook and other clients):
1. CalDAV handle_put never set is_all_day, so client-PUT VALUE=DATE events
   were stored timed (midnight UTC) and re-emitted by the ICS feed as
   DTSTART;TZID=<tz>:<date>T100000 — Outlook showed all-day events as
   10:00-10:00 next day in UTC+10.
2. Web-created all-day events stored midnight-local-tz converted to UTC,
   but emitters took .date() on the naive UTC value — all-day events
   rendered one day early for non-UTC timezones.
3. raw_ics for web-created all-day events carried a bare DTSTART date with
   no VALUE=DATE parameter — invalid DATE-TIME for strict CalDAV clients.

Post-fix convention: all-day dtstart/dtend = wall date at UTC midnight;
emitters emit DTSTART;VALUE=DATE. This migration rewrites stored rows to
the new convention and regenerates raw_ics for server-generated all-day
events. Client-PUT raw_ics blobs are preserved verbatim.

Revision ID: 006
Revises: 005
Create Date: 2026-09-20

"""
import os
import re
from datetime import datetime, timezone as dt_timezone
from typing import Sequence, Union
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa

revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DATE_DTSTART_RE = re.compile(r"^DTSTART[^:]*VALUE=DATE", re.IGNORECASE | re.MULTILINE)
_BARE_DATE_DTSTART_RE = re.compile(r"^DTSTART:\d{8}\s*$", re.IGNORECASE | re.MULTILINE)


def _as_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _wall_date_midnight(naive_utc: datetime, tz: ZoneInfo) -> datetime:
    aware = naive_utc.replace(tzinfo=dt_timezone.utc).astimezone(tz)
    return datetime.combine(aware.date(), datetime.min.time())


def upgrade() -> None:
    default_tz_name = os.environ.get("DEFAULT_TIMEZONE", "UTC") or "UTC"
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, uid, summary, description, dtstart, dtend, location, "
            "rrule, color, is_all_day, timezone, raw_ics FROM events"
        )
    ).mappings().fetchall()

    from app.caldav.ics_parser import generate_ics

    for row in rows:
        tz_name = row["timezone"] or default_tz_name
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")

        raw = row["raw_ics"] or ""
        is_all_day = bool(row["is_all_day"]) or bool(
            _DATE_DTSTART_RE.search(raw) or _BARE_DATE_DTSTART_RE.search(raw)
        )
        if not is_all_day:
            continue

        dtstart = _as_datetime(row["dtstart"])
        dtend = _as_datetime(row["dtend"]) if row["dtend"] is not None else None

        # Midnight UTC is already normalized (parse/import convention); any
        # other time is the old midnight-local-tz storage — recover the wall
        # date via the event timezone.
        if dtstart.time() != datetime.min.time():
            dtstart = _wall_date_midnight(dtstart, tz)
        if dtend is not None and dtend.time() != datetime.min.time():
            dtend = _wall_date_midnight(dtend, tz)

        updates = {"dtstart": dtstart, "dtend": dtend, "is_all_day": True}

        if "-//KalenDAV Server//EN" in raw:
            updates["raw_ics"] = generate_ics(
                uid=row["uid"],
                summary=row["summary"] or "",
                dtstart=dtstart,
                dtend=dtend,
                description=row["description"],
                location=row["location"],
                rrule=row["rrule"],
                is_all_day=True,
                color=row["color"],
                timezone=row["timezone"],
            )

        bind.execute(
            sa.text(
                "UPDATE events SET dtstart = :dtstart, dtend = :dtend, "
                "is_all_day = :is_all_day, raw_ics = :raw_ics WHERE id = :id"
            ),
            {
                "dtstart": updates["dtstart"],
                "dtend": updates["dtend"],
                "is_all_day": 1,
                "raw_ics": updates.get("raw_ics", raw),
                "id": row["id"],
            },
        )


def downgrade() -> None:
    # No safe downgrade — the original tz-shifted values and stale raw_ics
    # blobs cannot be recovered. Restore from backup instead.
    pass
