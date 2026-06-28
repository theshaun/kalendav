"""Characterization tests for app/ics_feed/router.py.

Exercises the /ics/{calendar_id} feed over HTTP: api-key auth (query param) and
HTTP Basic auth, plus the access-control matrix (owner / share / unrelated) and
the expiry/inactive/wrong-key 401 paths.
"""
from datetime import datetime, timedelta

import pytest

from app.models.share import SharePermission
from tests.conftest import basic_auth_header, make_api_key, make_calendar, make_event, make_share, make_user


@pytest.mark.asyncio
async def test_ics_feed_valid_api_key_owner(client, db_session):
    owner = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, owner.id, name="Alice Cal", color="#FF0000")
    await make_event(db_session, cal.id, uid="f-1", summary="Feed Event",
                     dtstart=datetime(2026, 6, 1, 10, 0, 0))
    _, plain = await make_api_key(db_session, owner.id, name="k")
    resp = await client.get(f"/ics/{cal.id}?api_key={plain}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    assert "X-WR-CALNAME:Alice Cal" in resp.text
    assert "Feed Event" in resp.text


@pytest.mark.asyncio
async def test_ics_feed_basic_auth_owner(client, db_session):
    owner = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, owner.id, name="C")
    resp = await client.get(f"/ics/{cal.id}", headers=basic_auth_header("alice", "pw"))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ics_feed_wrong_api_key_returns_401(client, db_session):
    owner = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, owner.id, name="C")
    resp = await client.get(f"/ics/{cal.id}?api_key=nonexistent-key")
    assert resp.status_code == 401
    assert "Invalid API key" in resp.text


@pytest.mark.asyncio
async def test_ics_feed_inactive_api_key_returns_401(client, db_session):
    owner = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, owner.id, name="C")
    api_key, plain = await make_api_key(db_session, owner.id, name="k")
    api_key.is_active = False
    db_session.add(api_key)
    await db_session.commit()
    resp = await client.get(f"/ics/{cal.id}?api_key={plain}")
    assert resp.status_code == 401
    assert "Invalid API key" in resp.text


@pytest.mark.asyncio
async def test_ics_feed_expired_api_key_returns_401(client, db_session):
    owner = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, owner.id, name="C")
    api_key, plain = await make_api_key(db_session, owner.id, name="k")
    api_key.expires_at = datetime.utcnow() - timedelta(days=1)
    db_session.add(api_key)
    await db_session.commit()
    resp = await client.get(f"/ics/{cal.id}?api_key={plain}")
    assert resp.status_code == 401
    assert "expired" in resp.text.lower()


@pytest.mark.asyncio
async def test_ics_feed_basic_auth_wrong_password_returns_401(client, db_session):
    owner = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, owner.id, name="C")
    resp = await client.get(f"/ics/{cal.id}", headers=basic_auth_header("alice", "wrong"))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ics_feed_no_auth_returns_401(client, db_session):
    owner = await make_user(db_session, username="alice", password="pw")
    cal = await make_calendar(db_session, owner.id, name="C")
    resp = await client.get(f"/ics/{cal.id}")
    assert resp.status_code == 401
    assert "Authentication required" in resp.text


@pytest.mark.asyncio
async def test_ics_feed_unrelated_user_returns_403(client, db_session):
    owner = await make_user(db_session, username="alice", password="pw")
    other = await make_user(db_session, username="bob", password="pw")
    cal = await make_calendar(db_session, owner.id, name="C")
    _, plain = await make_api_key(db_session, other.id, name="k")
    # other has no share on owner's calendar
    resp = await client.get(f"/ics/{cal.id}?api_key={plain}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ics_feed_read_share_via_api_key_allowed(client, db_session):
    owner = await make_user(db_session, username="alice", password="pw")
    reader = await make_user(db_session, username="bob", password="pw")
    cal = await make_calendar(db_session, owner.id, name="C")
    await make_share(db_session, cal.id, reader.id, SharePermission.READ)
    _, plain = await make_api_key(db_session, reader.id, name="k")
    # reader's api key + READ share -> feed accessible (read access is sufficient)
    resp = await client.get(f"/ics/{cal.id}?api_key={plain}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ics_feed_unknown_calendar_returns_404(client, db_session):
    owner = await make_user(db_session, username="alice", password="pw")
    _, plain = await make_api_key(db_session, owner.id, name="k")
    resp = await client.get("/ics/9999?api_key={plain}".replace("{plain}", plain))
    assert resp.status_code == 404
