from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.admin.router import _parse_form_dt


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
