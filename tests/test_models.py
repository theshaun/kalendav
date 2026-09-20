"""Model-level tests for the Task table.

Pins: (a) a Task inserts + round-trips through the in-memory fixture,
(b) the (calendar_id, uid) unique index raises IntegrityError on collision,
(c) TaskStatus enum values match the RFC 5545 VTODO status strings.
"""
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from app.models import Task, TaskStatus
from tests.conftest import make_calendar, make_task, make_user


async def test_task_insert_and_query_round_trip(db_session):
    # Given a calendar owned by a seeded user
    user = await make_user(db_session, username="u1")
    cal = await make_calendar(db_session, user.id)

    # When a Task is seeded against that calendar
    task = await make_task(db_session, cal.id, summary="Buy milk")

    # Then it round-trips through the DB with the expected fields
    fetched = (await db_session.execute(
        select(Task).where(Task.id == task.id)
    )).scalar_one()
    assert fetched.id == task.id
    assert fetched.calendar_id == cal.id
    assert fetched.summary == "Buy milk"
    assert fetched.status == "NEEDS-ACTION"  # default
    assert fetched.percent_complete is None
    assert fetched.raw_ics.startswith("BEGIN:VCALENDAR")


async def test_duplicate_calendar_uid_raises_integrity_error(db_session):
    # Given a calendar and one Task with (cal_id, "dup-uid")
    user = await make_user(db_session, username="u1")
    cal = await make_calendar(db_session, user.id)
    await make_task(db_session, cal.id, uid="dup-uid", summary="first")

    # When a second Task with the same (calendar_id, uid) is inserted
    # Then the unique index ix_tasks_calendar_uid rejects it
    with pytest.raises(IntegrityError):
        await make_task(db_session, cal.id, uid="dup-uid", summary="second")
        await db_session.flush()


def test_task_status_enum_values_match_rfc5545():
    assert TaskStatus.COMPLETED.value == "COMPLETED"
    assert TaskStatus.NEEDS_ACTION.value == "NEEDS-ACTION"
    assert TaskStatus.IN_PROCESS.value == "IN-PROCESS"
    assert TaskStatus.CANCELLED.value == "CANCELLED"
