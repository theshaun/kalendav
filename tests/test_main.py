from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.admin.router import _parse_form_dt
from tests.conftest import basic_auth_header, make_calendar, make_user


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_admin_unauthorized(client):
    response = await client.get("/admin/")
    # LoginRequiredException handler (app/main.py:24-25) returns a 302
    # redirect to /admin/login, raised before any DB query.
    assert response.status_code == 302


def test_parse_form_dt_all_day_ignores_client_tz():
    # All-day DATEs have no timezone: the wall date stores at UTC midnight.
    # Regression: a Brisbane user's 2026-09-20 all-day event was stored as
    # 2026-09-19T14:00 and rendered a day early in feeds.
    bne = ZoneInfo("Australia/Brisbane")
    assert _parse_form_dt("2026-09-20", bne, True) == datetime(2026, 9, 20, 0, 0, 0)
    assert _parse_form_dt("2026-09-20T00:00", bne, True) == datetime(2026, 9, 20, 0, 0, 0)
    assert _parse_form_dt("2026-09-23", bne, True) == datetime(2026, 9, 23, 0, 0, 0)
    assert _parse_form_dt(None, bne, True) is None
    assert _parse_form_dt("garbage", bne, True) is None


def test_parse_form_dt_timed_converts_client_tz_to_utc():
    bne = ZoneInfo("Australia/Brisbane")
    assert _parse_form_dt(
        "2026-09-20T09:00", bne, False
    ) == datetime(2026, 9, 19, 23, 0, 0)
    parsed = _parse_form_dt("2026-09-20T09:00:00+10:00", bne, False)
    assert parsed == datetime(2026, 9, 19, 23, 0, 0)
    assert parsed.tzinfo is None


@pytest.mark.asyncio
async def test_calendar_events_renders_put_all_day_as_all_day(client, db_session):
    # Regression (web calendar symptom): a multi-day VALUE=DATE event PUT via
    # CalDAV was stored is_all_day=False, so GET /admin/calendar/events sent
    # FullCalendar a timed 10:00-10:00 event (midnight UTC + server tz offset)
    # instead of allDay:true with date-only bounds.
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C", is_default=True)
    put_body = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Test//EN\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:web-allday@test\r\n"
        "SUMMARY:Trip\r\n"
        "DTSTART;VALUE=DATE:20260920\r\n"
        "DTEND;VALUE=DATE:20260923\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    ).encode()
    resp = await client.request(
        "PUT", f"/dav/alice/calendars/{cal.id}/web-allday@test.ics",
        headers=basic_auth_header("alice", "pw"), content=put_body,
    )
    assert resp.status_code == 201

    login = await client.post(
        "/admin/login", data={"username": "alice", "password": "pw"}
    )
    assert login.status_code == 302

    events_resp = await client.get(
        "/admin/calendar/events",
        params={"start": "2026-09-01", "end": "2026-10-01", "tz": "Australia/Brisbane"},
    )
    assert events_resp.status_code == 200
    events = events_resp.json()
    trip = next(e for e in events if e["title"] == "Trip")
    assert trip["allDay"] is True
    assert trip["start"] == "2026-09-20"
    assert trip["end"] == "2026-09-23"


@pytest.mark.asyncio
async def test_all_day_save_round_trip_keeps_dates(client, db_session):
    # Regression ("save pushes the day back"): update_event used to convert
    # all-day dates via the client tz (Sep 20 -> 2026-09-19T14:00 UTC), so a
    # Brisbane user saving an untouched event shifted it a day early.
    from app.models import Event

    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    login = await client.post("/admin/login", data={"username": "alice", "password": "pw"})
    assert login.status_code == 302

    create = await client.post(
        "/admin/calendar/events",
        data={
            "calendar_id": cal.id,
            "summary": "Trip",
            "dtstart": "2026-09-20",
            "dtend": "2026-09-23",
            "is_all_day": "true",
            "tz": "Australia/Brisbane",
        },
    )
    assert create.status_code == 200

    result = await db_session.execute(Event.__table__.select().where(Event.summary == "Trip"))
    row = result.one()
    assert row.dtstart == datetime(2026, 9, 20, 0, 0, 0)
    assert row.dtend == datetime(2026, 9, 23, 0, 0, 0)
    event_id = row.id

    save = await client.put(
        f"/admin/calendar/events/{event_id}",
        data={
            "calendar_id": cal.id,
            "summary": "Trip",
            "dtstart": "2026-09-20",
            "dtend": "2026-09-23",
            "is_all_day": "true",
            "tz": "Australia/Brisbane",
        },
    )
    assert save.status_code == 200

    result = await db_session.execute(
        Event.__table__.select().where(Event.id == event_id)
    )
    row = result.one()
    assert row.dtstart == datetime(2026, 9, 20, 0, 0, 0)
    assert row.dtend == datetime(2026, 9, 23, 0, 0, 0)

    events = (await client.get(
        "/admin/calendar/events",
        params={"start": "2026-09-01", "end": "2026-10-01", "tz": "Australia/Brisbane"},
    )).json()
    trip = next(e for e in events if e["title"] == "Trip")
    assert trip["allDay"] is True
    assert trip["start"] == "2026-09-20"
    assert trip["end"] == "2026-09-23"


@pytest.mark.asyncio
async def test_timed_save_round_trip_keeps_wall_clock(client, db_session):
    from app.models import Event

    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    login = await client.post("/admin/login", data={"username": "alice", "password": "pw"})
    assert login.status_code == 302

    create = await client.post(
        "/admin/calendar/events",
        data={
            "calendar_id": cal.id,
            "summary": "Meeting",
            "dtstart": "2026-09-20T09:00",
            "dtend": "2026-09-20T10:00",
            "tz": "Australia/Brisbane",
        },
    )
    assert create.status_code == 200

    result = await db_session.execute(Event.__table__.select().where(Event.summary == "Meeting"))
    row = result.one()
    assert row.dtstart == datetime(2026, 9, 19, 23, 0, 0)
    assert row.dtend == datetime(2026, 9, 20, 0, 0, 0)

    events = (await client.get(
        "/admin/calendar/events",
        params={"start": "2026-09-01", "end": "2026-10-01", "tz": "Australia/Brisbane"},
    )).json()
    meeting = next(e for e in events if e["title"] == "Meeting")
    assert meeting["allDay"] is False
    assert meeting["start"].startswith("2026-09-20T09:00")

    save = await client.put(
        f"/admin/calendar/events/{row.id}",
        data={
            "calendar_id": cal.id,
            "summary": "Meeting",
            "dtstart": "2026-09-20T09:00",
            "dtend": "2026-09-20T10:00",
            "tz": "Australia/Brisbane",
        },
    )
    assert save.status_code == 200

    result = await db_session.execute(
        Event.__table__.select().where(Event.id == row.id)
    )
    updated = result.one()
    assert updated.dtstart == datetime(2026, 9, 19, 23, 0, 0)
