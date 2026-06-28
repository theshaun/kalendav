"""Characterization tests for app/caldav/router.py — the CalDAV protocol layer.

Exercises every handler over HTTP via the conftest client + real HTTP Basic auth
against a seeded bcrypt user. Pins current behavior including known quirks
(none fixed — product frozen).
"""
from datetime import datetime

import pytest
from lxml import etree
from sqlalchemy import select

from app.models import Calendar, Event
from app.models.share import SharePermission
from tests.conftest import basic_auth_header, make_calendar, make_event, make_share, make_user

D = "{DAV:}"
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
async def test_get_calendar_event_path_quirk_returns_404(client, db_session):
    # QUIRK: handle_get requires len(path_parts) >= 5 for the calendar path,
    # but /dav/{user}/calendars/{cal_id}/{uid}.ics is only 4 parts, so it 404s.
    owner = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, owner.id, name="C")
    ev = await make_event(db_session, cal.id, uid="q", summary="Q",
                          dtstart=datetime(2026, 6, 1, 10, 0, 0))
    resp = await client.get(
        f"/dav/alice/calendars/{cal.id}/{ev.uid}.ics",
        headers=basic_auth_header("alice", "pw"),
    )
    assert resp.status_code == 404


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
    assert rows[0].summary == "Second"


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
