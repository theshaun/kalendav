"""Characterization tests for app/services/event_service.py and calendar_service.py.

DB-backed; uses the conftest in-memory engine + seeders. Pins current behavior
including the update_event color=Ellipsis sentinel quirk.
"""
from datetime import datetime, timedelta

import pytest

from app.models.share import SharePermission
from app.services.calendar_service import CalendarService
from app.services.event_service import EventService
from tests.conftest import make_calendar, make_event, make_share, make_user


# ---------- CalendarService ----------

@pytest.mark.asyncio
async def test_calendar_service_create_get_round_trip(db_session):
    user = await make_user(db_session, username="u1")
    svc = CalendarService(db_session)
    cal = await svc.create(user.id, name="Work", description="desc", color="#FF0000")
    assert cal.id is not None
    fetched = await svc.get_by_id(cal.id)
    assert fetched.name == "Work"
    assert fetched.description == "desc"
    assert fetched.color == "#FF0000"


@pytest.mark.asyncio
async def test_calendar_service_get_by_user(db_session):
    user = await make_user(db_session, username="u1")
    svc = CalendarService(db_session)
    await svc.create(user.id, name="A")
    await svc.create(user.id, name="B")
    cals = await svc.get_by_user(user.id)
    assert {c.name for c in cals} == {"A", "B"}


@pytest.mark.asyncio
async def test_calendar_service_update(db_session):
    user = await make_user(db_session, username="u1")
    svc = CalendarService(db_session)
    cal = await svc.create(user.id, name="Old")
    updated = await svc.update(cal.id, name="New", color="#00FF00")
    assert updated.name == "New"
    assert updated.color == "#00FF00"


@pytest.mark.asyncio
async def test_calendar_service_update_missing_returns_none(db_session):
    svc = CalendarService(db_session)
    assert await svc.update(9999, name="X") is None


@pytest.mark.asyncio
async def test_calendar_service_delete(db_session):
    user = await make_user(db_session, username="u1")
    svc = CalendarService(db_session)
    cal = await svc.create(user.id, name="Gone")
    assert await svc.delete(cal.id) is True
    assert await svc.get_by_id(cal.id) is None


@pytest.mark.asyncio
async def test_calendar_service_delete_missing_returns_false(db_session):
    svc = CalendarService(db_session)
    assert await svc.delete(9999) is False


# ---------- EventService: CRUD ----------

@pytest.mark.asyncio
async def test_event_service_create_event_generates_uid_and_raw_ics(db_session):
    user = await make_user(db_session, username="u1")
    cal = await make_calendar(db_session, user.id)
    svc = EventService(db_session)
    ev = await svc.create_event(
        cal.id, summary="Meeting", dtstart=datetime(2026, 1, 1, 10, 0, 0),
        dtend=datetime(2026, 1, 1, 11, 0, 0), description="d", location="l",
    )
    assert ev.uid  # generated uuid
    assert ev.raw_ics  # generated ICS body
    assert ev.summary == "Meeting"
    fetched = await svc.get_by_uid(cal.id, ev.uid)
    assert fetched is not None
    assert fetched.id == ev.id


@pytest.mark.asyncio
async def test_event_service_get_by_calendar_window_filter(db_session):
    user = await make_user(db_session, username="u1")
    cal = await make_calendar(db_session, user.id)
    svc = EventService(db_session)
    await make_event(db_session, cal.id, summary="past",
                     dtstart=datetime(2026, 1, 1, 9, 0, 0), dtend=datetime(2026, 1, 1, 10, 0, 0))
    await make_event(db_session, cal.id, summary="in",
                     dtstart=datetime(2026, 6, 1, 9, 0, 0), dtend=datetime(2026, 6, 1, 10, 0, 0))
    window = await svc.get_by_calendar(
        cal.id, start=datetime(2026, 5, 1, 0, 0, 0), end=datetime(2026, 7, 1, 0, 0, 0))
    assert [e.summary for e in window] == ["in"]


@pytest.mark.asyncio
async def test_event_service_update_event_regenerates_raw_ics(db_session):
    user = await make_user(db_session, username="u1")
    cal = await make_calendar(db_session, user.id)
    svc = EventService(db_session)
    ev = await svc.create_event(cal.id, summary="Old", dtstart=datetime(2026, 1, 1, 10, 0, 0))
    old_raw = ev.raw_ics
    updated = await svc.update_event(ev.id, summary="New Summary")
    assert updated.summary == "New Summary"
    assert updated.raw_ics != old_raw  # raw_ics regenerated


@pytest.mark.asyncio
async def test_event_service_update_event_color_sentinel_unchanged_when_omitted(db_session):
    # QUIRK: update_event uses color=... (Ellipsis) sentinel; omitting color
    # leaves the existing color unchanged (event_service.py:217, :233).
    user = await make_user(db_session, username="u1")
    cal = await make_calendar(db_session, user.id)
    svc = EventService(db_session)
    ev = await svc.create_event(cal.id, summary="S", dtstart=datetime(2026, 1, 1, 10, 0, 0), color="#FF0000")
    updated = await svc.update_event(ev.id, summary="S2")
    assert updated.color == "#FF0000"  # unchanged


@pytest.mark.asyncio
async def test_event_service_update_event_color_set_to_none(db_session):
    # QUIRK: passing color=None DOES set it (None is not Ellipsis) -> event.color=None
    user = await make_user(db_session, username="u1")
    cal = await make_calendar(db_session, user.id)
    svc = EventService(db_session)
    ev = await svc.create_event(cal.id, summary="S", dtstart=datetime(2026, 1, 1, 10, 0, 0), color="#FF0000")
    updated = await svc.update_event(ev.id, color=None)
    assert updated.color is None


@pytest.mark.asyncio
async def test_event_service_delete(db_session):
    user = await make_user(db_session, username="u1")
    cal = await make_calendar(db_session, user.id)
    svc = EventService(db_session)
    ev = await svc.create_event(cal.id, summary="X", dtstart=datetime(2026, 1, 1, 10, 0, 0))
    assert await svc.delete(ev.id) is True
    assert await svc.get_by_id(ev.id) is None


@pytest.mark.asyncio
async def test_event_service_delete_missing_returns_false(db_session):
    svc = EventService(db_session)
    assert await svc.delete(9999) is False


@pytest.mark.asyncio
async def test_event_service_import_events_count(db_session):
    user = await make_user(db_session, username="u1")
    cal = await make_calendar(db_session, user.id)
    svc = EventService(db_session)
    events_data = [
        {"uid": "a", "summary": "A", "dtstart": datetime(2026, 1, 1, 10, 0, 0), "raw_ics": "x"},
        {"uid": "b", "summary": "B", "dtstart": datetime(2026, 2, 1, 10, 0, 0), "raw_ics": "y"},
    ]
    count = await svc.import_events(cal.id, events_data)
    assert count == 2
    assert await svc.get_by_uid(cal.id, "a") is not None


# ---------- EventService: permission helpers ----------

async def _seed_permission_setup(db_session):
    owner = await make_user(db_session, username="owner")
    other = await make_user(db_session, username="other")
    cal_other = await make_calendar(db_session, other.id, name="OtherOwn")
    cal_read = await make_calendar(db_session, owner.id, name="ReadShared")
    cal_write = await make_calendar(db_session, owner.id, name="WriteShared")
    cal_private = await make_calendar(db_session, owner.id, name="Private")
    await make_share(db_session, cal_read.id, other.id, SharePermission.READ)
    await make_share(db_session, cal_write.id, other.id, SharePermission.WRITE)
    ev_read = await make_event(db_session, cal_read.id, summary="R",
                               dtstart=datetime(2026, 1, 1, 10, 0, 0))
    ev_write = await make_event(db_session, cal_write.id, summary="W",
                                dtstart=datetime(2026, 1, 1, 10, 0, 0))
    ev_priv = await make_event(db_session, cal_private.id, summary="P",
                               dtstart=datetime(2026, 1, 1, 10, 0, 0))
    return owner, other, cal_other, cal_read, cal_write, ev_read, ev_write, ev_priv


@pytest.mark.asyncio
async def test_accessible_calendars_includes_owned_and_all_shares(db_session):
    _, other, cal_other, cal_read, cal_write, *_ = await _seed_permission_setup(db_session)
    svc = EventService(db_session)
    accessible = await svc.get_user_accessible_calendars(other.id)
    assert {cal_other.id, cal_read.id, cal_write.id} <= set(accessible)


@pytest.mark.asyncio
async def test_writable_calendars_excludes_read_only(db_session):
    _, other, cal_other, cal_read, cal_write, *_ = await _seed_permission_setup(db_session)
    svc = EventService(db_session)
    writable = await svc.get_writable_calendars(other.id)
    assert cal_other.id in writable
    assert cal_write.id in writable
    assert cal_read.id not in writable  # READ-only excluded


@pytest.mark.asyncio
async def test_can_access_event_read_share_true_edit_false(db_session):
    _, other, _, _, _, ev_read, *_ = await _seed_permission_setup(db_session)
    svc = EventService(db_session)
    assert await svc.can_access_event(ev_read.id, other.id) is True
    assert await svc.can_edit_event(ev_read.id, other.id) is False


@pytest.mark.asyncio
async def test_can_edit_event_write_share_true(db_session):
    _, other, _, _, _, _, ev_write, _ = await _seed_permission_setup(db_session)
    svc = EventService(db_session)
    assert await svc.can_access_event(ev_write.id, other.id) is True
    assert await svc.can_edit_event(ev_write.id, other.id) is True


@pytest.mark.asyncio
async def test_cannot_access_unrelated_event(db_session):
    _, other, _, _, _, _, _, ev_priv = await _seed_permission_setup(db_session)
    svc = EventService(db_session)
    assert await svc.can_access_event(ev_priv.id, other.id) is False
    assert await svc.can_edit_event(ev_priv.id, other.id) is False


@pytest.mark.asyncio
async def test_can_access_event_missing_event_false(db_session):
    svc = EventService(db_session)
    assert await svc.can_access_event(9999, 1) is False
    assert await svc.can_edit_event(9999, 1) is False


# ---------- EventService: lower-level create/update (raw_ics-passing variants) ----------

@pytest.mark.asyncio
async def test_event_service_create_raw_ics_variant(db_session):
    user = await make_user(db_session, username="u1")
    cal = await make_calendar(db_session, user.id)
    svc = EventService(db_session)
    ev = await svc.create(
        cal.id, uid="raw-uid", raw_ics="RAWCONTENT",
        summary="Raw", description="D",
        dtstart=datetime(2026, 1, 1, 10, 0, 0), dtend=datetime(2026, 1, 1, 11, 0, 0),
        location="L", color="#000000",
    )
    assert ev.uid == "raw-uid"
    assert ev.raw_ics == "RAWCONTENT"
    assert ev.summary == "Raw"
    assert ev.color == "#000000"


@pytest.mark.asyncio
async def test_event_service_update_raw_ics_variant(db_session):
    user = await make_user(db_session, username="u1")
    cal = await make_calendar(db_session, user.id)
    svc = EventService(db_session)
    ev = await svc.create(cal.id, uid="u", raw_ics="OLD",
                          summary="S", dtstart=datetime(2026, 1, 1, 10, 0, 0))
    updated = await svc.update(
        ev.id, summary="S2", description="D2",
        dtstart=datetime(2026, 2, 1, 10, 0, 0), dtend=datetime(2026, 2, 1, 11, 0, 0),
        location="L2", rrule="FREQ=DAILY", raw_ics="NEW", color="#111111",
    )
    assert updated.summary == "S2"
    assert updated.description == "D2"
    assert updated.location == "L2"
    assert updated.rrule == "FREQ=DAILY"
    assert updated.raw_ics == "NEW"
    assert updated.color == "#111111"


@pytest.mark.asyncio
async def test_event_service_update_missing_returns_none(db_session):
    svc = EventService(db_session)
    assert await svc.update(9999, summary="X") is None


# ---------- EventService: get_events_for_user (owned + shared) ----------

@pytest.mark.asyncio
async def test_get_events_for_user_spans_owned_and_shared_calendars(db_session):
    owner = await make_user(db_session, username="owner")
    other = await make_user(db_session, username="other")
    cal_own = await make_calendar(db_session, other.id, name="Own")
    cal_shared = await make_calendar(db_session, owner.id, name="Shared")
    cal_private = await make_calendar(db_session, owner.id, name="Private")
    await make_share(db_session, cal_shared.id, other.id, SharePermission.READ)

    await make_event(db_session, cal_own.id, summary="mine",
                     dtstart=datetime(2026, 6, 1, 10, 0, 0))
    await make_event(db_session, cal_shared.id, summary="shared",
                     dtstart=datetime(2026, 6, 2, 10, 0, 0))
    await make_event(db_session, cal_private.id, summary="hidden",
                     dtstart=datetime(2026, 6, 3, 10, 0, 0))

    svc = EventService(db_session)
    events = await svc.get_events_for_user(other.id)
    summaries = {e.summary for e in events}
    assert "mine" in summaries
    assert "shared" in summaries
    assert "hidden" not in summaries  # not accessible to other


@pytest.mark.asyncio
async def test_get_events_for_user_no_calendars_returns_empty(db_session):
    user = await make_user(db_session, username="lone")
    svc = EventService(db_session)
    assert await svc.get_events_for_user(user.id) == []
