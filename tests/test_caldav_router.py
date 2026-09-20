"""Characterization tests for app/caldav/router.py — the CalDAV protocol layer.

Exercises every handler over HTTP via the conftest client + real HTTP Basic auth
against a seeded bcrypt user. Pins current behavior including known quirks
(none fixed — product frozen).
"""
from datetime import datetime

import pytest
from lxml import etree
from sqlalchemy import select

from app.models import Calendar, Event, Task
from app.models.share import SharePermission
from tests.conftest import basic_auth_header, make_api_key, make_calendar, make_event, make_share, make_task, make_user

D = "{DAV:}"
C = "{urn:ietf:params:xml:ns:caldav}"
ICAL = "{http://apple.com/ns/ical/}"

PUT_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:{uid}
SUMMARY:{summary}
DTSTART:20260601T100000Z
DTEND:20260601T110000Z
END:VEVENT
END:VCALENDAR
"""

PUT_VTODO_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VTODO
UID:{uid}
DTSTAMP:20260701T000000Z
SUMMARY:{summary}
STATUS:{status}
END:VTODO
END:VCALENDAR
"""


def _propupdate(props_xml: str) -> bytes:
    return (
        '<?xml version="1.0"?>'
        '<d:propertyupdate xmlns:d="DAV:" xmlns:ical="http://apple.com/ns/ical/">'
        f'<d:set><d:prop>{props_xml}</d:prop></d:set>'
        "</d:propertyupdate>"
    ).encode()


# ---------- OPTIONS ----------

@pytest.mark.asyncio
async def test_options_announces_dav_capabilities(client):
    resp = await client.request("OPTIONS", "/dav/")
    assert resp.status_code == 200
    assert "calendar-access" in resp.headers.get("DAV", "")
    allow = resp.headers.get("Allow", "")
    for verb in ("PROPFIND", "PUT", "DELETE", "REPORT", "MKCALENDAR"):
        assert verb in allow


# ---------- PROPFIND ----------

@pytest.mark.asyncio
async def test_propfind_root_returns_principal(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    resp = await client.request("PROPFIND", "/dav/", headers=basic_auth_header("alice", "pw"))
    assert resp.status_code == 207
    root = etree.fromstring(resp.content)
    assert root.tag == f"{D}multistatus"


@pytest.mark.asyncio
async def test_propfind_single_calendar_depth1_lists_events(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="Work")
    ev = await make_event(db_session, cal.id, uid="ev-1", summary="Meeting",
                          dtstart=datetime(2026, 6, 1, 10, 0, 0))
    headers = {**basic_auth_header("alice", "pw"), "Depth": "1"}
    resp = await client.request(
        "PROPFIND", f"/dav/alice/calendars/{cal.id}/", headers=headers
    )
    assert resp.status_code == 207
    root = etree.fromstring(resp.content)
    hrefs = [h.text for h in root.iter(f"{D}href")]
    assert any(h.endswith(f"{ev.uid}.ics") for h in hrefs)


@pytest.mark.asyncio
async def test_propfind_unknown_calendar_id_returns_404(client, db_session):
    await make_user(db_session, username="alice", password="pw")
    resp = await client.request(
        "PROPFIND", "/dav/alice/calendars/9999/", headers=basic_auth_header("alice", "pw")
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_propfind_non_numeric_calendar_id_returns_404(client, db_session):
    await make_user(db_session, username="alice", password="pw")
    resp = await client.request(
        "PROPFIND", "/dav/alice/calendars/abc/", headers=basic_auth_header("alice", "pw")
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_propfind_principals_calendars_lists_owned_and_shared(client, db_session):
    owner = await make_user(db_session, username="alice", password="pw")
    other = await make_user(db_session, username="bob", password="pw")
    cal_own = await make_calendar(db_session, owner.id, name="Own")
    cal_shared = await make_calendar(db_session, owner.id, name="Shared")
    await make_share(db_session, cal_shared.id, other.id, SharePermission.READ)

    headers = {**basic_auth_header("bob", "pw"), "Depth": "1"}
    resp = await client.request("PROPFIND", "/dav/principals/bob/calendars/", headers=headers)
    assert resp.status_code == 207
    root = etree.fromstring(resp.content)
    hrefs = [h.text for h in root.iter(f"{D}href")]
    assert any(str(cal_shared.id) in h for h in hrefs)


@pytest.mark.asyncio
async def test_propfind_calendars_path_lists_user_calendars(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal_a = await make_calendar(db_session, user.id, name="A")
    cal_b = await make_calendar(db_session, user.id, name="B")
    headers = {**basic_auth_header("alice", "pw"), "Depth": "1"}
    resp = await client.request("PROPFIND", "/dav/alice/calendars/", headers=headers)
    assert resp.status_code == 207
    root = etree.fromstring(resp.content)
    hrefs = [h.text for h in root.iter(f"{D}href")]
    assert any(str(cal_a.id) in h for h in hrefs)
    assert any(str(cal_b.id) in h for h in hrefs)


# ---------- PROPPATCH ----------

@pytest.mark.asyncio
async def test_proppatch_renames_and_sets_color(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="Old")
    body = _propupdate(
        "<d:displayname>Renamed</d:displayname>"
        "<ical:calendar-color>#AABBCC</ical:calendar-color>"
    )
    resp = await client.request(
        "PROPPATCH", f"/dav/alice/calendars/{cal.id}/",
        headers=basic_auth_header("alice", "pw"), content=body,
    )
    assert resp.status_code == 207
    # read via Core select to bypass the ORM identity map (db_session cached the
    # pre-update cal object with expire_on_commit=False; MKCALENDAR uses this pattern).
    result = await db_session.execute(
        Calendar.__table__.select().where(Calendar.id == cal.id)
    )
    row = result.one()
    assert row.name == "Renamed"
    assert row.color == "#AABBCC"


@pytest.mark.asyncio
async def test_proppatch_truncates_alpha_color_to_seven_chars(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    body = _propupdate("<ical:calendar-color>#AABBCCFF</ical:calendar-color>")
    await client.request(
        "PROPPATCH", f"/dav/alice/calendars/{cal.id}/",
        headers=basic_auth_header("alice", "pw"), content=body,
    )
    result = await db_session.execute(
        Calendar.__table__.select().where(Calendar.id == cal.id)
    )
    row = result.one()
    assert row.color == "#AABBCC"  # 8-char alpha truncated to 7


@pytest.mark.asyncio
async def test_proppatch_read_only_share_returns_403(client, db_session):
    owner = await make_user(db_session, username="alice", password="pw")
    reader = await make_user(db_session, username="reader", password="pw")
    cal = await make_calendar(db_session, owner.id, name="Shared")
    await make_share(db_session, cal.id, reader.id, SharePermission.READ)
    body = _propupdate("<d:displayname>Hacked</d:displayname>")
    resp = await client.request(
        "PROPPATCH", f"/dav/alice/calendars/{cal.id}/",
        headers=basic_auth_header("reader", "pw"), content=body,
    )
    assert resp.status_code == 403


# ---------- MKCALENDAR ----------

@pytest.mark.asyncio
async def test_mkcalendar_creates_calendar(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    body = _propupdate(
        "<d:displayname>Brand New</d:displayname>"
        "<d:description>A desc</d:description>"
        "<ical:calendar-color>#00FF00</ical:calendar-color>"
    )
    resp = await client.request(
        "MKCALENDAR", "/dav/alice/calendars/newcal/",
        headers=basic_auth_header("alice", "pw"), content=body,
    )
    assert resp.status_code == 201
    result = await db_session.execute(Calendar.__table__.select())
    rows = result.fetchall()
    created = [r for r in rows if r.name == "Brand New"]
    assert len(created) == 1
    assert created[0].description == "A desc"
    assert created[0].color == "#00FF00"


@pytest.mark.asyncio
async def test_mkcalendar_bad_path_returns_400(client, db_session):
    await make_user(db_session, username="alice", password="pw")
    # path missing the 'calendars' segment
    resp = await client.request(
        "MKCALENDAR", "/dav/alice/newcal/",
        headers=basic_auth_header("alice", "pw"), content=b"",
    )
    assert resp.status_code == 400


# ---------- GET ----------

@pytest.mark.asyncio
async def test_get_single_event_from_default_calendar(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="Def", is_default=True)
    ev = await make_event(db_session, cal.id, uid="getme", summary="G",
                          dtstart=datetime(2026, 6, 1, 10, 0, 0))
    resp = await client.get(
        f"/dav/{ev.uid}.ics", headers=basic_auth_header("alice", "pw")
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VEVENT" in resp.text


@pytest.mark.asyncio
async def test_get_unknown_event_returns_404(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    await make_calendar(db_session, user.id, name="Def", is_default=True)
    resp = await client.get(
        "/dav/nope.ics", headers=basic_auth_header("alice", "pw")
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_calendar_event_path_returns_single_event(client, db_session):
    # B1 fix: this 4-part path now returns the single Event (was a 404 quirk before).
    owner = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, owner.id, name="C")
    ev = await make_event(db_session, cal.id, uid="q", summary="Q-Ev",
                          dtstart=datetime(2026, 6, 1, 10, 0, 0))
    resp = await client.get(
        f"/dav/alice/calendars/{cal.id}/{ev.uid}.ics",
        headers=basic_auth_header("alice", "pw"),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VEVENT" in resp.text
    assert ev.uid in resp.text


# ---------- PUT ----------

@pytest.mark.asyncio
async def test_put_creates_event_with_etag(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    body = PUT_ICS.format(uid="put-1", summary="Put One").encode()
    resp = await client.request(
        "PUT", f"/dav/alice/calendars/{cal.id}/put-1.ics",
        headers=basic_auth_header("alice", "pw"), content=body,
    )
    assert resp.status_code == 201
    assert "ETag" in resp.headers
    # event persisted with the uid parsed from the ICS body
    result = await db_session.execute(Event.__table__.select())
    rows = result.fetchall()
    assert any(r.uid == "put-1" for r in rows)


@pytest.mark.asyncio
async def test_put_same_uid_updates_existing(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    body1 = PUT_ICS.format(uid="put-2", summary="First").encode()
    body2 = PUT_ICS.format(uid="put-2", summary="Second").encode()
    await client.request(
        "PUT", f"/dav/alice/calendars/{cal.id}/put-2.ics",
        headers=basic_auth_header("alice", "pw"), content=body1,
    )
    await client.request(
        "PUT", f"/dav/alice/calendars/{cal.id}/put-2.ics",
        headers=basic_auth_header("alice", "pw"), content=body2,
    )
    result = await db_session.execute(
        Event.__table__.select().where(Event.uid == "put-2")
    )
    rows = result.fetchall()
    assert len(rows) == 1  # updated in place, not duplicated


@pytest.mark.asyncio
async def test_put_with_tzid_round_trips_through_get(client, db_session):
    # Regression: CalDAV clients (iPhone, DAVx5) PUT events with TZID parameters.
    # The server must preserve the TZID so a subsequent GET returns the same
    # wall-clock the client sent, not a UTC-shifted value.
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C", is_default=True)
    put_body = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Test//EN\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:tz-rt@test\r\n"
        "SUMMARY:BNE Event\r\n"
        "DTSTART;TZID=Australia/Brisbane:20260715T090000\r\n"
        "DTEND;TZID=Australia/Brisbane:20260715T100000\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    ).encode()
    resp = await client.request(
        "PUT", f"/dav/alice/calendars/{cal.id}/tz-rt@test.ics",
        headers=basic_auth_header("alice", "pw"), content=put_body,
    )
    assert resp.status_code == 201

    # event.timezone column captured the original TZID
    result = await db_session.execute(
        Event.__table__.select().where(Event.uid == "tz-rt@test")
    )
    row = result.one()
    assert row.timezone == "Australia/Brisbane"

    # GET regenerates via generate_calendar_ics which now uses event.timezone:
    # 09:00 BNE stored as 23:00 UTC (prev day) -> converted back to 09:00 BNE
    get_resp = await client.get(
        "/dav/tz-rt@test.ics",
        headers=basic_auth_header("alice", "pw"),
    )
    assert get_resp.status_code == 200
    assert "DTSTART;TZID=Australia/Brisbane:20260715T090000" in get_resp.text


@pytest.mark.asyncio
async def test_put_all_day_value_date_sets_flag_and_feed_renders_date(client, db_session):
    # Regression (Outlook symptom): handle_put never set is_all_day, so a
    # client-PUT multi-day VALUE=DATE event was re-emitted by the ICS feed as
    # DTSTART;TZID=Australia/Brisbane:...T100000 — all-day events showed as
    # 10:00-10:00 next day in UTC+10 clients.
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C", is_default=True)
    put_body = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Test//EN\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:allday-rt@test\r\n"
        "SUMMARY:Trip\r\n"
        "DTSTART;VALUE=DATE:20260920\r\n"
        "DTEND;VALUE=DATE:20260923\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    ).encode()
    resp = await client.request(
        "PUT", f"/dav/alice/calendars/{cal.id}/allday-rt@test.ics",
        headers=basic_auth_header("alice", "pw"), content=put_body,
    )
    assert resp.status_code == 201

    result = await db_session.execute(
        Event.__table__.select().where(Event.uid == "allday-rt@test")
    )
    row = result.one()
    assert row.is_all_day == 1
    assert row.dtstart == datetime(2026, 9, 20, 0, 0, 0)
    assert row.dtend == datetime(2026, 9, 23, 0, 0, 0)

    _, plain = await make_api_key(db_session, user.id, name="k")
    feed = await client.get(f"/ics/{cal.id}?api_key={plain}")
    assert feed.status_code == 200
    assert "DTSTART;VALUE=DATE:20260920" in feed.text
    assert "DTEND;VALUE=DATE:20260923" in feed.text
    assert "T100000" not in feed.text


@pytest.mark.asyncio
async def test_put_short_path_auto_creates_default_calendar(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    # user has NO calendars yet
    body = PUT_ICS.format(uid="put-3", summary="Auto").encode()
    resp = await client.request(
        "PUT", "/dav/put-3.ics",
        headers=basic_auth_header("alice", "pw"), content=body,
    )
    assert resp.status_code == 201
    result = await db_session.execute(Calendar.__table__.select())
    rows = result.fetchall()
    assert any(r.user_id == user.id for r in rows)  # default calendar auto-created


@pytest.mark.asyncio
async def test_put_read_only_share_returns_403(client, db_session):
    owner = await make_user(db_session, username="alice", password="pw")
    reader = await make_user(db_session, username="reader", password="pw")
    cal = await make_calendar(db_session, owner.id, name="C")
    await make_share(db_session, cal.id, reader.id, SharePermission.READ)
    body = PUT_ICS.format(uid="put-4", summary="X").encode()
    resp = await client.request(
        "PUT", f"/dav/alice/calendars/{cal.id}/put-4.ics",
        headers=basic_auth_header("reader", "pw"), content=body,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_put_write_share_allowed(client, db_session):
    owner = await make_user(db_session, username="alice", password="pw")
    writer = await make_user(db_session, username="writer", password="pw")
    cal = await make_calendar(db_session, owner.id, name="C")
    await make_share(db_session, cal.id, writer.id, SharePermission.WRITE)
    body = PUT_ICS.format(uid="put-5", summary="W").encode()
    resp = await client.request(
        "PUT", f"/dav/alice/calendars/{cal.id}/put-5.ics",
        headers=basic_auth_header("writer", "pw"), content=body,
    )
    assert resp.status_code == 201


# ---------- DELETE ----------

@pytest.mark.asyncio
async def test_delete_existing_event_returns_204(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    ev = await make_event(db_session, cal.id, uid="del-1", summary="D",
                          dtstart=datetime(2026, 6, 1, 10, 0, 0))
    resp = await client.request(
        "DELETE", f"/dav/alice/calendars/{cal.id}/{ev.uid}.ics",
        headers=basic_auth_header("alice", "pw"),
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_is_idempotent(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    ev = await make_event(db_session, cal.id, uid="del-2", summary="D",
                          dtstart=datetime(2026, 6, 1, 10, 0, 0))
    headers = basic_auth_header("alice", "pw")
    path = f"/dav/alice/calendars/{cal.id}/{ev.uid}.ics"
    assert (await client.request("DELETE", path, headers=headers)).status_code == 204
    # second delete still 204 (current idempotent behavior)
    assert (await client.request("DELETE", path, headers=headers)).status_code == 204


@pytest.mark.asyncio
async def test_delete_read_only_share_returns_403(client, db_session):
    owner = await make_user(db_session, username="alice", password="pw")
    reader = await make_user(db_session, username="reader", password="pw")
    cal = await make_calendar(db_session, owner.id, name="C")
    ev = await make_event(db_session, cal.id, uid="del-3", summary="D",
                          dtstart=datetime(2026, 6, 1, 10, 0, 0))
    await make_share(db_session, cal.id, reader.id, SharePermission.READ)
    resp = await client.request(
        "DELETE", f"/dav/alice/calendars/{cal.id}/{ev.uid}.ics",
        headers=basic_auth_header("reader", "pw"),
    )
    assert resp.status_code == 403


# ---------- REPORT ----------

@pytest.mark.asyncio
async def test_report_returns_all_calendar_events(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    await make_event(db_session, cal.id, uid="r-1", summary="R1",
                     dtstart=datetime(2026, 6, 1, 10, 0, 0))
    await make_event(db_session, cal.id, uid="r-2", summary="R2",
                     dtstart=datetime(2026, 6, 2, 10, 0, 0))
    resp = await client.request(
        "REPORT", f"/dav/alice/calendars/{cal.id}/",
        headers=basic_auth_header("alice", "pw"), content=b"",
    )
    assert resp.status_code == 207
    root = etree.fromstring(resp.content)
    hrefs = [h.text for h in root.iter(f"{D}href")]
    assert any("r-1.ics" in h for h in hrefs)
    assert any("r-2.ics" in h for h in hrefs)


@pytest.mark.asyncio
async def test_report_response_includes_sync_token_at_multistatus_level(client, db_session):
    # Regression: without <d:sync-token> as a direct child of <d:multistatus>,
    # the .NET Dav.Client library's .Single() call throws InvalidOperationException.
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    await make_event(db_session, cal.id, uid="r-1", summary="R1",
                     dtstart=datetime(2026, 6, 1, 10, 0, 0))
    resp = await client.request(
        "REPORT", f"/dav/alice/calendars/{cal.id}/",
        headers=basic_auth_header("alice", "pw"), content=b"",
    )
    assert resp.status_code == 207
    root = etree.fromstring(resp.content)
    # <d:sync-token> must be a direct child of <d:multistatus>, not nested in a response
    direct_tokens = [c for c in root if etree.QName(c).localname == "sync-token"]
    assert len(direct_tokens) == 1, "exactly one multistatus-level sync-token required (RFC 6578 §3.4)"
    assert direct_tokens[0].text
    assert direct_tokens[0].text.startswith("http"), "token should be a stable opaque URI"


@pytest.mark.asyncio
async def test_report_sync_token_advances_on_event_change(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    e1 = await make_event(db_session, cal.id, uid="adv-1", summary="V1",
                          dtstart=datetime(2026, 6, 1, 10, 0, 0))

    async def current_token() -> str:
        resp = await client.request(
            "REPORT", f"/dav/alice/calendars/{cal.id}/",
            headers=basic_auth_header("alice", "pw"), content=b"",
        )
        root = etree.fromstring(resp.content)
        tokens = [c for c in root if etree.QName(c).localname == "sync-token"]
        return tokens[0].text

    token_before = await current_token()

    e1.summary = "V2"
    await db_session.commit()

    token_after_update = await current_token()
    assert token_after_update != token_before, "token must advance when an event is updated"

    await make_event(db_session, cal.id, uid="adv-2", summary="V3",
                     dtstart=datetime(2026, 6, 2, 10, 0, 0))
    token_after_add = await current_token()
    assert token_after_add != token_after_update, "token must advance when an event is added"


@pytest.mark.asyncio
async def test_propfind_advertises_matching_sync_token(client, db_session):
    # Clients use PROPFIND's sync-token property to decide whether to re-sync.
    # It must match what REPORT returns, else clients either never sync (stale)
    # or loop (always newer).
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    await make_event(db_session, cal.id, uid="m-1", summary="M1",
                     dtstart=datetime(2026, 6, 1, 10, 0, 0))

    propfind = await client.request(
        "PROPFIND", f"/dav/alice/calendars/{cal.id}/",
        headers=basic_auth_header("alice", "pw"),
        content=_propupdate("<d:prop><d:sync-token/></d:prop>"),
    )
    assert propfind.status_code == 207
    propfind_root = etree.fromstring(propfind.content)
    propfind_tokens = propfind_root.iter(f"{D}sync-token")
    propfind_token = next(propfind_tokens).text

    report = await client.request(
        "REPORT", f"/dav/alice/calendars/{cal.id}/",
        headers=basic_auth_header("alice", "pw"), content=b"",
    )
    report_root = etree.fromstring(report.content)
    report_token = next(
        c.text for c in report_root if etree.QName(c).localname == "sync-token"
    )

    assert propfind_token == report_token, (
        "PROPFIND sync-token property must match REPORT multistatus sync-token"
    )


@pytest.mark.asyncio
async def test_report_read_share_allowed(client, db_session):
    owner = await make_user(db_session, username="alice", password="pw")
    reader = await make_user(db_session, username="reader", password="pw")
    cal = await make_calendar(db_session, owner.id, name="C")
    await make_event(db_session, cal.id, uid="r-3", summary="R3",
                     dtstart=datetime(2026, 6, 1, 10, 0, 0))
    await make_share(db_session, cal.id, reader.id, SharePermission.READ)
    resp = await client.request(
        "REPORT", f"/dav/alice/calendars/{cal.id}/",
        headers=basic_auth_header("reader", "pw"), content=b"",
    )
    assert resp.status_code == 207


# ---------- VTODO ----------

@pytest.mark.asyncio
async def test_propfind_advertises_vtodo(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    headers = {**basic_auth_header("alice", "pw"), "Depth": "1"}
    resp = await client.request(
        "PROPFIND", f"/dav/alice/calendars/{cal.id}/", headers=headers
    )
    assert resp.status_code == 207
    root = etree.fromstring(resp.content)
    comp_names = {
        c.get("name")
        for c in root.iter(f"{C}comp")
        if c.get("name") is not None
    }
    assert "VEVENT" in comp_names, "calendar must still advertise VEVENT"
    assert "VTODO" in comp_names, "calendar must advertise VTODO (T4)"


@pytest.mark.asyncio
async def test_put_get_delete_vtodo(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    body = PUT_VTODO_ICS.format(uid="vtodo-1", summary="Walk the dog", status="NEEDS-ACTION").encode()
    put_resp = await client.request(
        "PUT", f"/dav/alice/calendars/{cal.id}/vtodo-1.ics",
        headers=basic_auth_header("alice", "pw"), content=body,
    )
    assert put_resp.status_code == 201
    assert "ETag" in put_resp.headers

    result = await db_session.execute(Task.__table__.select())
    rows = result.fetchall()
    assert any(r.uid == "vtodo-1" for r in rows), "PUT must persist a Task row"

    get_resp = await client.get(
        f"/dav/alice/calendars/{cal.id}/vtodo-1.ics",
        headers=basic_auth_header("alice", "pw"),
    )
    assert get_resp.status_code == 200
    assert get_resp.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VTODO" in get_resp.text

    del_resp = await client.request(
        "DELETE", f"/dav/alice/calendars/{cal.id}/vtodo-1.ics",
        headers=basic_auth_header("alice", "pw"),
    )
    assert del_resp.status_code == 204
    after = await db_session.execute(Task.__table__.select())
    assert not any(r.uid == "vtodo-1" for r in after.fetchall())


@pytest.mark.asyncio
async def test_get_single_vtodo_not_merged_calendar(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    # Negative-assertion seed: an unrelated VEVENT in the same calendar.
    await make_event(db_session, cal.id, uid="other-ev", summary="OtherEv",
                     dtstart=datetime(2026, 6, 1, 10, 0, 0))
    await make_task(db_session, cal.id, uid="single-vtodo", summary="Only Task")

    resp = await client.get(
        f"/dav/alice/calendars/{cal.id}/single-vtodo.ics",
        headers=basic_auth_header("alice", "pw"),
    )
    assert resp.status_code == 200
    assert "BEGIN:VTODO" in resp.text
    assert "Only Task" in resp.text
    assert "BEGIN:VEVENT" not in resp.text, "single-resource GET must not merge the calendar"
    assert "OtherEv" not in resp.text


@pytest.mark.asyncio
async def test_sync_token_changes_on_task_put(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")

    async def current_token() -> str:
        resp = await client.request(
            "PROPFIND", f"/dav/alice/calendars/{cal.id}/",
            headers=basic_auth_header("alice", "pw"),
        )
        root = etree.fromstring(resp.content)
        tokens = list(root.iter(f"{D}sync-token"))
        assert tokens, "PROPFIND must return a sync-token"
        return tokens[0].text

    before = await current_token()
    body = PUT_VTODO_ICS.format(uid="sync-t", summary="Syncer", status="NEEDS-ACTION").encode()
    put_resp = await client.request(
        "PUT", f"/dav/alice/calendars/{cal.id}/sync-t.ics",
        headers=basic_auth_header("alice", "pw"), content=body,
    )
    assert put_resp.status_code == 201
    after = await current_token()
    assert before != after, "sync-token must advance when a Task is PUT (B2 fix)"


@pytest.mark.asyncio
async def test_vevent_regression(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    body = PUT_ICS.format(uid="vev-1", summary="Still Works").encode()
    put_resp = await client.request(
        "PUT", f"/dav/alice/calendars/{cal.id}/vev-1.ics",
        headers=basic_auth_header("alice", "pw"), content=body,
    )
    assert put_resp.status_code == 201
    assert "ETag" in put_resp.headers

    get_resp = await client.get(
        f"/dav/alice/calendars/{cal.id}/vev-1.ics",
        headers=basic_auth_header("alice", "pw"),
    )
    assert get_resp.status_code == 200
    assert "BEGIN:VEVENT" in get_resp.text

    del_resp = await client.request(
        "DELETE", f"/dav/alice/calendars/{cal.id}/vev-1.ics",
        headers=basic_auth_header("alice", "pw"),
    )
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_propfind_depth1_lists_tasks(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    await make_task(db_session, cal.id, uid="listed-task", summary="Listed")
    headers = {**basic_auth_header("alice", "pw"), "Depth": "1"}
    resp = await client.request(
        "PROPFIND", f"/dav/alice/calendars/{cal.id}/", headers=headers
    )
    assert resp.status_code == 207
    root = etree.fromstring(resp.content)
    hrefs = [h.text for h in root.iter(f"{D}href")]
    assert any(h and h.endswith("listed-task.ics") for h in hrefs), \
        "PROPFIND Depth:1 must list Task resources alongside Events"


@pytest.mark.asyncio
async def test_put_malformed_vtodo_does_not_500(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    # Empty VTODO — exercises the new VTODO branch; parse_vtodo never raises.
    malformed = (
        b"BEGIN:VCALENDAR\r\n"
        b"VERSION:2.0\r\n"
        b"BEGIN:VTODO\r\n"
        b"END:VTODO\r\n"
        b"END:VCALENDAR\r\n"
    )
    resp = await client.request(
        "PUT", f"/dav/alice/calendars/{cal.id}/malformed.ics",
        headers=basic_auth_header("alice", "pw"), content=malformed,
    )
    assert resp.status_code != 500, "malformed VTODO must not 500 (parse_vtodo is graceful)"
    assert resp.status_code == 201, f"unexpected status {resp.status_code}"


# ---------- REPORT calendar-query comp-filter (T5) ----------

# Canonical RFC 4791 §7.8.9 "pending-todos" query: VCALENDAR > VTODO with
# COMPLETED is-not-defined + STATUS text-match negate CANCELLED.
_PENDING_TODOS_QUERY = """<?xml version="1.0" encoding="UTF-8"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:getetag/>
    <c:calendar-data/>
  </d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR">
      <c:comp-filter name="VTODO">
        <c:prop-filter name="COMPLETED">
          <c:is-not-defined/>
        </c:prop-filter>
        <c:prop-filter name="STATUS">
          <c:text-match negate-condition="yes">CANCELLED</c:text-match>
        </c:prop-filter>
      </c:comp-filter>
    </c:comp-filter>
  </c:filter>
</c:calendar-query>
"""

_VTODO_ONLY_QUERY = """<?xml version="1.0" encoding="UTF-8"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:getetag/>
    <c:calendar-data/>
  </d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR">
      <c:comp-filter name="VTODO"/>
    </c:comp-filter>
  </c:filter>
</c:calendar-query>
"""

_VEVENT_ONLY_QUERY = """<?xml version="1.0" encoding="UTF-8"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:getetag/>
    <c:calendar-data/>
  </d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR">
      <c:comp-filter name="VEVENT"/>
    </c:comp-filter>
  </c:filter>
</c:calendar-query>
"""

# A non-calendar-query REPORT root. Must fall back to the prior all-events
# behavior (M4 gate) — sync-collection consumers see no change.
_SYNC_COLLECTION_SHAPED = """<?xml version="1.0" encoding="UTF-8"?>
<d:sync-collection xmlns:d="DAV:">
  <d:sync-token/>
  <d:prop>
    <d:getetag/>
  </d:prop>
</d:sync-collection>
"""


def _response_uids(root: etree._Element) -> set[str]:
    """Pull the trailing {uid}.ics segment off every returned <d:href>."""
    uids: set[str] = set()
    for href in root.iter(f"{D}href"):
        text = href.text or ""
        if text.endswith(".ics"):
            uids.add(text.rsplit("/", 1)[-1][: -len(".ics")])
    return uids


@pytest.mark.asyncio
async def test_report_vtodo_comp_filter(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    await make_event(db_session, cal.id, uid="evt-1", summary="Evt",
                     dtstart=datetime(2026, 6, 1, 10, 0, 0))
    await make_task(db_session, cal.id, uid="todo-active",
                    summary="Active", status="NEEDS-ACTION")
    await make_task(db_session, cal.id, uid="todo-done",
                    summary="Done", status="COMPLETED",
                    completed=datetime(2026, 6, 1, 12, 0, 0),
                    percent_complete=100)

    resp = await client.request(
        "REPORT", f"/dav/alice/calendars/{cal.id}/",
        headers=basic_auth_header("alice", "pw"),
        content=_PENDING_TODOS_QUERY.encode(),
    )
    assert resp.status_code == 207
    root = etree.fromstring(resp.content)
    uids = _response_uids(root)

    assert "todo-active" in uids, "pending VTODO must be returned"
    assert "todo-done" not in uids, (
        "COMPLETED VTODO must be dropped by COMPLETED is-not-defined"
    )
    assert "evt-1" not in uids, "VEVENT must be excluded (only VTODO requested)"
    assert uids == {"todo-active"}, f"expected exactly one VTODO, got {uids}"


@pytest.mark.asyncio
async def test_report_vevent_comp_filter(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    await make_event(db_session, cal.id, uid="evt-1", summary="Evt",
                     dtstart=datetime(2026, 6, 1, 10, 0, 0))
    await make_task(db_session, cal.id, uid="todo-1", summary="T")

    resp = await client.request(
        "REPORT", f"/dav/alice/calendars/{cal.id}/",
        headers=basic_auth_header("alice", "pw"),
        content=_VEVENT_ONLY_QUERY.encode(),
    )
    assert resp.status_code == 207
    root = etree.fromstring(resp.content)
    uids = _response_uids(root)
    assert "evt-1" in uids
    assert "todo-1" not in uids


@pytest.mark.asyncio
async def test_report_vtodo_only_excludes_events(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    await make_event(db_session, cal.id, uid="evt-1", summary="Evt",
                     dtstart=datetime(2026, 6, 1, 10, 0, 0))
    await make_task(db_session, cal.id, uid="todo-1", summary="T1")
    await make_task(db_session, cal.id, uid="todo-2", summary="T2")

    resp = await client.request(
        "REPORT", f"/dav/alice/calendars/{cal.id}/",
        headers=basic_auth_header("alice", "pw"),
        content=_VTODO_ONLY_QUERY.encode(),
    )
    assert resp.status_code == 207
    root = etree.fromstring(resp.content)
    uids = _response_uids(root)
    assert uids == {"todo-1", "todo-2"}, f"expected both tasks, got {uids}"


@pytest.mark.asyncio
async def test_report_unparseable_body_fallback(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    await make_event(db_session, cal.id, uid="evt-1", summary="Evt",
                     dtstart=datetime(2026, 6, 1, 10, 0, 0))
    await make_task(db_session, cal.id, uid="todo-1", summary="T")

    resp = await client.request(
        "REPORT", f"/dav/alice/calendars/{cal.id}/",
        headers=basic_auth_header("alice", "pw"),
        content=b"this is not xml <<<",
    )
    assert resp.status_code == 207, "malformed REPORT body must not raise 500"
    root = etree.fromstring(resp.content)
    uids = _response_uids(root)
    # Fallback path returns events only (no tasks) — preserves prior behavior.
    assert "evt-1" in uids
    assert "todo-1" not in uids


@pytest.mark.asyncio
async def test_report_non_calendar_query_unchanged(client, db_session):
    user = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, user.id, name="C")
    await make_event(db_session, cal.id, uid="evt-1", summary="Evt",
                     dtstart=datetime(2026, 6, 1, 10, 0, 0))
    await make_task(db_session, cal.id, uid="todo-1", summary="T")

    resp = await client.request(
        "REPORT", f"/dav/alice/calendars/{cal.id}/",
        headers=basic_auth_header("alice", "pw"),
        content=_SYNC_COLLECTION_SHAPED.encode(),
    )
    assert resp.status_code == 207
    root = etree.fromstring(resp.content)
    uids = _response_uids(root)
    assert "evt-1" in uids
    assert "todo-1" not in uids, "non-calendar-query path must surface no tasks"
