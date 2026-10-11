from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.admin.router import _parse_form_dt
from tests.conftest import basic_auth_header, make_calendar, make_event, make_user


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_root_redirects_to_admin(client):
    response = await client.get("/", follow_redirects=False)
    assert response.status_code in (301, 302, 307, 308)
    assert response.headers["location"].rstrip("/") == "/admin"


@pytest.mark.asyncio
async def test_calendar_events_filter_by_calendar_param(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal_a = await make_calendar(db_session, user.id, name="A")
    cal_b = await make_calendar(db_session, user.id, name="B")
    mallory = await make_user(db_session, username="mallory", password="pw")
    cal_m = await make_calendar(db_session, mallory.id, name="M")
    await make_event(db_session, cal_a.id, summary="InA",
                     dtstart=datetime(2026, 10, 5, 1, 0), dtend=datetime(2026, 10, 5, 2, 0))
    await make_event(db_session, cal_b.id, summary="InB",
                     dtstart=datetime(2026, 10, 6, 1, 0), dtend=datetime(2026, 10, 6, 2, 0))
    await make_event(db_session, cal_m.id, summary="NotVisible",
                     dtstart=datetime(2026, 10, 7, 1, 0), dtend=datetime(2026, 10, 7, 2, 0))
    login = await client.post("/admin/login", data={"username": "alice", "password": "pw"})
    assert login.status_code == 302

    async def titles(**params):
        resp = await client.get("/admin/calendar/events", params={
            "start": "2026-10-01", "end": "2026-11-01", "tz": "UTC", **params,
        })
        assert resp.status_code == 200
        return [e["title"] for e in resp.json()]

    assert await titles(calendar=cal_a.id) == ["InA"]
    assert await titles(calendar=cal_b.id) == ["InB"]
    # An inaccessible calendar id is ignored (no leak, no empty view).
    got = await titles(calendar=cal_m.id)
    assert sorted(got) == ["InA", "InB"]
    assert sorted(await titles()) == ["InA", "InB"]


@pytest.mark.asyncio
async def test_my_calendars_rows_have_calendar_and_task_links(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="A")
    login = await client.post("/admin/login", data={"username": "alice", "password": "pw"})
    assert login.status_code == 302

    resp = await client.get("/admin/my-calendars")
    assert resp.status_code == 200
    body = resp.text
    assert f'href="/admin/calendar?calendar={cal.id}"' in body
    assert f'href="/admin/tasks?calendar={cal.id}"' in body


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


async def _login(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    login = await client.post("/admin/login", data={"username": "alice", "password": "pw"})
    assert login.status_code == 302
    return cal


@pytest.mark.asyncio
async def test_create_recurring_all_day_yearly_never(client, db_session):
    # Regression: the event modal always posts rrule_until (empty for
    # end_type=never) — fromisoformat("") raised, the bare except fell into
    # strptime("", "%Y-%m-%d") which raised uncaught -> HTTP 500.
    from app.models import Event

    cal = await _login(client, db_session)

    resp = await client.post(
        "/admin/calendar/events",
        data={
            "calendar_id": cal.id,
            "summary": "Wedding Anniversary",
            "dtstart": "2026-10-11",
            "dtend": "",
            "is_all_day": "on",
            "location": "",
            "description": "",
            "color": "#06b6d4",
            "rrule_freq": "yearly",
            "rrule_interval": "1",
            "rrule_end_type": "never",
            "rrule_count": "10",
            "rrule_until": "",
            "tz": "Australia/Brisbane",
        },
    )
    assert resp.status_code == 200

    result = await db_session.execute(
        Event.__table__.select().where(Event.summary == "Wedding Anniversary")
    )
    row = result.one()
    # end_type=never must ignore the stale count=10 sitting in the form.
    assert row.rrule == "FREQ=YEARLY"
    assert row.is_all_day is True
    assert row.dtstart == datetime(2026, 10, 11, 0, 0, 0)
    assert row.dtend == datetime(2026, 10, 12, 0, 0, 0)


@pytest.mark.asyncio
async def test_create_recurring_count_end_type_ignores_stale_until(client, db_session):
    from app.models import Event

    cal = await _login(client, db_session)

    resp = await client.post(
        "/admin/calendar/events",
        data={
            "calendar_id": cal.id,
            "summary": "PT",
            "dtstart": "2026-10-11T09:00",
            "dtend": "2026-10-11T10:00",
            "rrule_freq": "weekly",
            "rrule_interval": "2",
            "rrule_end_type": "count",
            "rrule_count": "5",
            "rrule_until": "",
            "tz": "Australia/Brisbane",
        },
    )
    assert resp.status_code == 200

    result = await db_session.execute(
        Event.__table__.select().where(Event.summary == "PT")
    )
    row = result.one()
    assert row.rrule == "FREQ=WEEKLY;INTERVAL=2;COUNT=5"


@pytest.mark.asyncio
async def test_create_recurring_until_end_type_ignores_stale_count(client, db_session):
    from app.models import Event

    cal = await _login(client, db_session)

    resp = await client.post(
        "/admin/calendar/events",
        data={
            "calendar_id": cal.id,
            "summary": "Standup",
            "dtstart": "2026-10-11T09:00",
            "dtend": "2026-10-11T09:30",
            "rrule_freq": "daily",
            "rrule_interval": "1",
            "rrule_end_type": "until",
            "rrule_count": "10",
            "rrule_until": "2030-01-01",
            "tz": "Australia/Brisbane",
        },
    )
    assert resp.status_code == 200

    result = await db_session.execute(
        Event.__table__.select().where(Event.summary == "Standup")
    )
    row = result.one()
    assert row.rrule == "FREQ=DAILY;UNTIL=20300101T000000Z"


@pytest.mark.asyncio
async def test_update_recurring_never_does_not_500(client, db_session):
    # update_event carried the same empty-until crash as create_event.
    from app.models import Event

    cal = await _login(client, db_session)

    create = await client.post(
        "/admin/calendar/events",
        data={
            "calendar_id": cal.id,
            "summary": "Anniv",
            "dtstart": "2026-10-11",
            "is_all_day": "on",
            "rrule_freq": "yearly",
            "rrule_end_type": "never",
            "rrule_count": "10",
            "rrule_until": "",
            "tz": "Australia/Brisbane",
        },
    )
    assert create.status_code == 200
    result = await db_session.execute(
        Event.__table__.select().where(Event.summary == "Anniv")
    )
    event_id = result.one().id

    save = await client.put(
        f"/admin/calendar/events/{event_id}",
        data={
            "calendar_id": cal.id,
            "summary": "Anniv",
            "dtstart": "2026-10-11",
            "is_all_day": "on",
            "rrule_freq": "yearly",
            "rrule_interval": "1",
            "rrule_end_type": "never",
            "rrule_count": "10",
            "rrule_until": "",
            "tz": "Australia/Brisbane",
        },
    )
    assert save.status_code == 200
    result = await db_session.execute(
        Event.__table__.select().where(Event.id == event_id)
    )
    assert result.one().rrule == "FREQ=YEARLY"


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
