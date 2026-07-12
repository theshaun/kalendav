"""Characterization tests for app/caldav/ics_parser.py pure functions.

These pin CURRENT behavior (including quirks). The parser is frozen product
code; tests assert what the code does, not what it ideally should do.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from icalendar import Calendar

from app.caldav.ics_parser import (
    build_rrule,
    convert_utc_to_tz,
    ensure_utc_naive,
    extract_tzid,
    generate_calendar_ics,
    generate_ics,
    parse_ics,
    parse_ics_bulk,
    parse_rrule_string,
)
from app.config import settings

UTC = timezone.utc


@pytest.fixture
def tz_utc(monkeypatch):
    """Force default_timezone=UTC so tests are deterministic regardless of .env."""
    monkeypatch.setattr(settings, "default_timezone", "UTC")


# ---------- ensure_utc_naive ----------

def test_ensure_utc_naive_none():
    assert ensure_utc_naive(None) is None


def test_ensure_utc_naive_naive_passthrough():
    dt = datetime(2026, 1, 1, 10, 0, 0)
    assert ensure_utc_naive(dt) == dt


def test_ensure_utc_naive_aware_converted_to_utc_naive():
    # 2026-01-01 10:00 in US/Eastern (UTC-5 in winter) is 15:00 UTC
    eastern = datetime(2026, 1, 1, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    result = ensure_utc_naive(eastern)
    assert result == datetime(2026, 1, 1, 15, 0, 0)
    assert result.tzinfo is None


# ---------- parse_ics ----------

FULL_EVENT_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:event-123@test
SUMMARY:Team Meeting
DESCRIPTION:Weekly sync
DTSTART:20260101T100000Z
DTEND:20260101T110000Z
LOCATION:Room A
RRULE:FREQ=WEEKLY;BYDAY=MO
X-APPLE-CALENDAR-COLOR:#FF0000
END:VEVENT
END:VCALENDAR
"""


def test_parse_ics_full_event():
    uid, summary, description, dtstart, dtend, location, rrule, color, tzid = parse_ics(FULL_EVENT_ICS)
    assert uid == "event-123@test"
    assert summary == "Team Meeting"
    assert description == "Weekly sync"
    assert dtstart == datetime(2026, 1, 1, 10, 0, 0)  # Z -> naive UTC
    assert dtend == datetime(2026, 1, 1, 11, 0, 0)
    assert location == "Room A"
    # QUIRK: parse_ics str()s icalendar's vRecur object, so rrule comes back as
    # a "vRecur({...})" repr, not the raw "FREQ=WEEKLY;BYDAY=MO" RFC5545 string.
    assert rrule.startswith("vRecur(")
    assert "WEEKLY" in rrule
    assert color == "#FF0000"
    # FULL_EVENT_ICS uses DTSTART:...Z so the original TZ is UTC.
    assert tzid == "UTC"


def test_parse_ics_all_day_date_combined_to_midnight():
    ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:allday@test
SUMMARY:Holiday
DTSTART;VALUE=DATE:20260101
END:VEVENT
END:VCALENDAR
"""
    uid, summary, description, dtstart, dtend, location, rrule, color, tzid = parse_ics(ics)
    assert uid == "allday@test"
    assert summary == "Holiday"
    # all-day date is combined to midnight datetime
    assert dtstart == datetime(2026, 1, 1, 0, 0, 0)
    assert dtend is None
    assert description is None
    assert location is None
    assert rrule is None
    assert color is None


def test_parse_ics_missing_dtstart_defaults_to_utcnow():
    ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:notime@test
SUMMARY:No time
END:VEVENT
END:VCALENDAR
"""
    before = datetime.utcnow()
    _, _, _, dtstart, _, _, _, _, _ = parse_ics(ics)
    after = datetime.utcnow()
    assert before <= dtstart <= after


def test_parse_ics_missing_uid_gets_generated_uuid():
    ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
SUMMARY:No UID
DTSTART:20260101T100000Z
END:VEVENT
END:VCALENDAR
"""
    uid, *_ = parse_ics(ics)
    # generated uid must be a valid uuid string
    assert str(uuid.UUID(uid)) == uid


def test_parse_ics_only_first_vevent_returned():
    ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:first@test
SUMMARY:First
DTSTART:20260101T100000Z
END:VEVENT
BEGIN:VEVENT
UID:second@test
SUMMARY:Second
DTSTART:20260102T100000Z
END:VEVENT
END:VCALENDAR
"""
    uid, summary, *_ = parse_ics(ics)
    # break semantics: only the first VEVENT is parsed
    assert uid == "first@test"
    assert summary == "First"


def test_parse_ics_rrule_returned_as_vrecur_repr():
    # QUIRK: regardless of an RRULE: prefix, parse_ics returns rrule as the
    # str() of icalendar's vRecur object ("vRecur({'FREQ': ['DAILY'], ...})"),
    # not the raw RFC5545 "FREQ=DAILY;INTERVAL=2" string.
    ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:rr@test
SUMMARY:RR
DTSTART:20260101T100000Z
RRULE:FREQ=DAILY;INTERVAL=2
END:VEVENT
END:VCALENDAR
"""
    *_, rrule, _, _ = parse_ics(ics)
    assert rrule.startswith("vRecur(")
    assert "DAILY" in rrule


# ---------- parse_ics_bulk ----------

TWO_EVENT_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:keep-1@test
SUMMARY:One
DTSTART:20260101T100000Z
END:VEVENT
BEGIN:VEVENT
UID:keep-2@test
SUMMARY:Two
DTSTART:20260201T080000
DTEND:20260201T090000
END:VEVENT
END:VCALENDAR
"""


def test_parse_ics_bulk_returns_all_events():
    events = parse_ics_bulk(TWO_EVENT_ICS)
    assert len(events) == 2
    assert [e["summary"] for e in events] == ["One", "Two"]


def test_parse_ics_bulk_regenerates_uid_as_uuid():
    events = parse_ics_bulk(TWO_EVENT_ICS)
    for e in events:
        # original UIDs (keep-1/keep-2) are replaced with fresh uuids
        assert str(uuid.UUID(e["uid"])) == e["uid"]
        assert e["uid"].startswith("keep-") is False
        assert e["raw_ics"]  # non-empty


def test_parse_ics_bulk_all_day_detection():
    ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:ad@test
SUMMARY:AllDay
DTSTART;VALUE=DATE:20260301
END:VEVENT
END:VCALENDAR
"""
    events = parse_ics_bulk(ics)
    assert len(events) == 1
    assert events[0]["is_all_day"] is True
    assert events[0]["dtstart"] == datetime(2026, 3, 1, 0, 0, 0)


def test_parse_ics_bulk_timed_not_all_day():
    events = parse_ics_bulk(TWO_EVENT_ICS)
    assert all(e["is_all_day"] is False for e in events)


# ---------- parse_rrule_string ----------

def test_parse_rrule_string_empty():
    assert parse_rrule_string("") == {}


def test_parse_rrule_string_none():
    assert parse_rrule_string(None) == {}


def test_parse_rrule_string_strips_prefix():
    assert parse_rrule_string("RRULE:FREQ=DAILY") == {"freq": "DAILY"}


@pytest.mark.parametrize("rrule,expected", [
    ("FREQ=DAILY;INTERVAL=2", {"freq": "DAILY", "interval": 2}),
    ("FREQ=WEEKLY;COUNT=10", {"freq": "WEEKLY", "count": 10}),
    ("FREQ=MONTHLY;BYMONTH=12", {"freq": "MONTHLY", "bymonth": 12}),
    ("FREQ=YEARLY;BYMONTHDAY=15", {"freq": "YEARLY", "bymonthday": 15}),
])
def test_parse_rrule_string_int_fields(rrule, expected):
    assert parse_rrule_string(rrule) == expected


def test_parse_rrule_string_int_fallback_to_str_on_invalid():
    # BYMONTH with non-numeric falls back to the raw string
    result = parse_rrule_string("BYMONTH=abc")
    assert result == {"bymonth": "abc"}


def test_parse_rrule_string_until_date():
    result = parse_rrule_string("UNTIL=20260101")
    assert result == {"until": date(2026, 1, 1)}


def test_parse_rrule_string_until_datetime():
    result = parse_rrule_string("UNTIL=20260101T100000Z")
    assert result == {"until": datetime(2026, 1, 1, 10, 0, 0)}


def test_parse_rrule_string_byday_list():
    result = parse_rrule_string("BYDAY=MO,WE,FR")
    assert result == {"byday": ["MO", "WE", "FR"]}


def test_parse_rrule_string_unknown_key_string_value():
    result = parse_rrule_string("FREQ=DAILY;WKST=MO")
    assert result == {"freq": "DAILY", "wkst": "MO"}


# ---------- convert_utc_to_tz ----------

def test_convert_utc_to_tz_none_passthrough():
    assert convert_utc_to_tz(None, "UTC") is None


def test_convert_utc_to_tz_naive_utc_to_utc(tz_utc):
    # UTC->UTC is identity (wall-clock unchanged).
    dt = datetime(2026, 1, 1, 10, 0, 0)
    out = convert_utc_to_tz(dt, "UTC")
    assert out == datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)


def test_convert_utc_to_tz_naive_utc_to_bne():
    # Brisbane is UTC+10: 10:00 UTC -> 20:00 Brisbane same day.
    dt = datetime(2026, 1, 1, 10, 0, 0)
    out = convert_utc_to_tz(dt, "Australia/Brisbane")
    assert out == datetime(2026, 1, 1, 20, 0, 0, tzinfo=ZoneInfo("Australia/Brisbane"))


def test_convert_utc_to_tz_aware_passthrough():
    aware = datetime(2026, 1, 1, 10, 0, 0, tzinfo=ZoneInfo("Australia/Brisbane"))
    # Aware datetimes return unchanged.
    assert convert_utc_to_tz(aware, "UTC") is aware


def test_convert_utc_to_tz_invalid_falls_back_to_instance_default(tz_utc):
    # Unknown tz name -> server default (UTC under tz_utc fixture) rather than raising.
    dt = datetime(2026, 1, 1, 10, 0, 0)
    out = convert_utc_to_tz(dt, "Not/A/Real_Zone")
    assert out.utcoffset() == timedelta(0)


# ---------- extract_tzid ----------

def test_extract_tzid_returns_iana_name_for_tzid_param():
    ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:tzid@test
SUMMARY:T
DTSTART;TZID=Australia/Brisbane:20260101T100000
END:VEVENT
END:VCALENDAR
"""
    from icalendar import Calendar
    cal = Calendar.from_ical(ics)
    for component in cal.walk():
        if component.name == "VEVENT":
            assert extract_tzid(component) == "Australia/Brisbane"
            return
    assert False, "no VEVENT found"


def test_extract_tzid_returns_utc_for_z_suffix():
    ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:utc@test
SUMMARY:U
DTSTART:20260101T100000Z
END:VEVENT
END:VCALENDAR
"""
    from icalendar import Calendar
    cal = Calendar.from_ical(ics)
    for component in cal.walk():
        if component.name == "VEVENT":
            assert extract_tzid(component) == "UTC"
            return
    assert False, "no VEVENT found"


def test_extract_tzid_returns_none_for_floating():
    ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:float@test
SUMMARY:F
DTSTART:20260101T100000
END:VEVENT
END:VCALENDAR
"""
    from icalendar import Calendar
    cal = Calendar.from_ical(ics)
    for component in cal.walk():
        if component.name == "VEVENT":
            assert extract_tzid(component) is None
            return
    assert False, "no VEVENT found"


def test_parse_ics_captures_tzid_parameter():
    ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:tzcap@test
SUMMARY:TZ
DTSTART;TZID=America/New_York:20260101T100000
DTEND;TZID=America/New_York:20260101T110000
END:VEVENT
END:VCALENDAR
"""
    *_, tzid = parse_ics(ics)
    assert tzid == "America/New_York"
    # DTSTART was 10:00 EST = 15:00 UTC; parse_ics returns naive UTC.
    _, _, _, dtstart, dtend, _, _, _, _ = parse_ics(ics)
    assert dtstart == datetime(2026, 1, 1, 15, 0, 0)
    assert dtend == datetime(2026, 1, 1, 16, 0, 0)


# ---------- generate_ics ----------

def test_generate_ics_timed_defaults_dtend_to_plus_one_hour(tz_utc):
    dtstart = datetime(2026, 1, 1, 10, 0, 0)
    out = generate_ics(uid="u1", summary="S", dtstart=dtstart)
    assert "BEGIN:VEVENT" in out
    assert "PRODID:-//KalenDAV Server//EN" in out
    cal = Calendar.from_ical(out)
    ev = list(cal.walk("VEVENT"))[0]
    # default dtend = dtstart + 1h, localized to instance tz
    assert ev.get("dtend").dt == dtstart.replace(tzinfo=UTC) + timedelta(hours=1)
    assert str(ev.get("uid")) == "u1"


def test_generate_ics_all_day_uses_vdate(tz_utc):
    dtstart = datetime(2026, 1, 1, 0, 0, 0)
    dtend = datetime(2026, 1, 2, 0, 0, 0)
    out = generate_ics(uid="u2", summary="AD", dtstart=dtstart, dtend=dtend, is_all_day=True)
    cal = Calendar.from_ical(out)
    ev = list(cal.walk("VEVENT"))[0]
    assert ev.get("dtstart").dt == date(2026, 1, 1)
    assert ev.get("dtend").dt == date(2026, 1, 2)


def test_generate_ics_includes_optional_fields(tz_utc):
    dtstart = datetime(2026, 1, 1, 10, 0, 0)
    out = generate_ics(
        uid="u3", summary="WithOpts", dtstart=dtstart,
        description="Desc", location="Loc", rrule="FREQ=DAILY;INTERVAL=2", color="#00FF00",
    )
    cal = Calendar.from_ical(out)
    ev = list(cal.walk("VEVENT"))[0]
    assert str(ev.get("description")) == "Desc"
    assert str(ev.get("location")) == "Loc"
    assert ev.get("rrule") is not None  # rrule dict added
    assert str(ev.get("X-APPLE-CALENDAR-COLOR")) == "#00FF00"


def test_generate_ics_round_trip_with_parse_ics(tz_utc):
    dtstart = datetime(2026, 1, 1, 10, 0, 0)
    dtend = datetime(2026, 1, 1, 11, 30, 0)
    out = generate_ics(
        uid="rt@test", summary="Round Trip", dtstart=dtstart, dtend=dtend,
        description="D", location="L",
    )
    uid, summary, description, parsed_start, parsed_end, location, _, _, _ = parse_ics(out)
    assert uid == "rt@test"
    assert summary == "Round Trip"
    assert description == "D"
    assert location == "L"
    # parse_ics uses ensure_utc_naive, so with UTC default the round-trip is identity
    assert parsed_start == dtstart
    assert parsed_end == dtend


def test_generate_ics_emits_utc_z_suffix_for_utc_default(tz_utc):
    dtstart = datetime(2026, 1, 1, 10, 0, 0)
    out = generate_ics(uid="tz1@test", summary="TZ", dtstart=dtstart)
    # icalendar special-cases UTC: emits Z suffix instead of ;TZID=UTC
    assert "DTSTART:20260101T100000Z" in out


def test_generate_ics_emits_tzid_for_custom_timezone(monkeypatch):
    monkeypatch.setattr(settings, "default_timezone", "Australia/Brisbane")
    # Stored dt is naive UTC 10:00; Brisbane is UTC+10, so wall-clock there is 20:00.
    dtstart = datetime(2026, 1, 1, 10, 0, 0)
    out = generate_ics(uid="tz2@test", summary="BNE", dtstart=dtstart)
    assert "DTSTART;TZID=Australia/Brisbane:20260101T200000" in out


def test_generate_ics_explicit_timezone_overrides_default(monkeypatch):
    monkeypatch.setattr(settings, "default_timezone", "UTC")
    # Passing timezone="Australia/Brisbane" should win over the UTC default.
    dtstart = datetime(2026, 1, 1, 10, 0, 0)
    out = generate_ics(
        uid="tz3@test", summary="BNE", dtstart=dtstart,
        timezone="Australia/Brisbane",
    )
    assert "X-WR-TIMEZONE:Australia/Brisbane" in out
    assert "DTSTART;TZID=Australia/Brisbane:20260101T200000" in out


def test_generate_ics_adds_x_wr_timezone_header(tz_utc):
    out = generate_ics(uid="h@test", summary="H", dtstart=datetime(2026, 1, 1, 10, 0, 0))
    assert "X-WR-TIMEZONE:UTC" in out


def test_generate_ics_skips_vtimezone_for_utc(tz_utc):
    out = generate_ics(uid="u@test", summary="U", dtstart=datetime(2026, 1, 1, 10, 0, 0))
    # UTC is implicit in RFC 5545; we don't add a VTIMEZONE block for it
    assert "BEGIN:VTIMEZONE" not in out


def test_generate_ics_includes_vtimezone_block(monkeypatch):
    monkeypatch.setattr(settings, "default_timezone", "Australia/Brisbane")
    out = generate_ics(uid="vt@test", summary="VT", dtstart=datetime(2026, 1, 1, 10, 0, 0))
    assert "BEGIN:VTIMEZONE" in out
    assert "TZID:Australia/Brisbane" in out


def test_generate_ics_aware_dtstart_passes_through(tz_utc):
    aware = datetime(2026, 1, 1, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    out = generate_ics(uid="aw@test", summary="AW", dtstart=aware)
    assert "DTSTART;TZID=America/New_York:20260101T100000" in out


# ---------- build_rrule ----------

def test_build_rrule_none_freq_returns_none():
    assert build_rrule("none") is None


def test_build_rrule_invalid_freq_returns_none():
    assert build_rrule("hourly") is None  # not in freq_map


@pytest.mark.parametrize("freq,expected", [
    ("daily", "FREQ=DAILY"),
    ("weekly", "FREQ=WEEKLY"),
    ("monthly", "FREQ=MONTHLY"),
    ("yearly", "FREQ=YEARLY"),
])
def test_build_rrule_basic_freqs(freq, expected):
    assert build_rrule(freq) == expected


def test_build_rrule_interval_only_when_gt_1():
    assert build_rrule("daily", interval=3) == "FREQ=DAILY;INTERVAL=3"
    assert build_rrule("daily", interval=1) == "FREQ=DAILY"  # interval=1 omitted


def test_build_rrule_count():
    assert build_rrule("daily", count=5) == "FREQ=DAILY;COUNT=5"


def test_build_rrule_until():
    until = datetime(2026, 1, 1, 0, 0, 0)
    assert build_rrule("daily", until=until) == "FREQ=DAILY;UNTIL=20260101T000000Z"


def test_build_rrule_byday_only_when_weekly():
    # byday included for weekly
    assert build_rrule("weekly", byday=["MO", "WE"]) == "FREQ=WEEKLY;BYDAY=MO,WE"
    # byday ignored for non-weekly
    assert build_rrule("monthly", byday=["MO"]) == "FREQ=MONTHLY"


def test_build_rrule_count_takes_precedence_over_until():
    until = datetime(2026, 1, 1, 0, 0, 0)
    assert build_rrule("daily", count=3, until=until) == "FREQ=DAILY;COUNT=3"


# ---------- generate_calendar_ics ----------

class _FakeEvent:
    """Minimal stand-in matching the attributes generate_calendar_ics reads."""
    def __init__(self, uid, dtstart, dtend=None, summary=None, description=None,
                 location=None, rrule=None, color=None, timezone=None):
        self.uid = uid
        self.dtstart = dtstart
        self.dtend = dtend
        self.summary = summary
        self.description = description
        self.location = location
        self.rrule = rrule
        self.color = color
        self.timezone = timezone


def test_generate_calendar_ics_includes_all_events_and_calname(tz_utc):
    e1 = _FakeEvent("a@test", datetime(2026, 1, 1, 10, 0, 0), summary="A")
    e2 = _FakeEvent("b@test", datetime(2026, 2, 1, 9, 0, 0), summary="B")
    out = generate_calendar_ics([e1, e2], calendar_name="My Cal", calendar_color="#123456")
    cal = Calendar.from_ical(out)
    assert str(cal.get("x-wr-calname")) == "My Cal"
    assert str(cal.get("x-apple-calendar-color")) == "#123456"
    uids = {str(ev.get("uid")) for ev in cal.walk("VEVENT")}
    assert uids == {"a@test", "b@test"}


def test_generate_calendar_ics_default_dtend_plus_one_hour(tz_utc):
    e = _FakeEvent("c@test", datetime(2026, 1, 1, 10, 0, 0), summary="C")  # no dtend
    out = generate_calendar_ics([e])
    cal = Calendar.from_ical(out)
    ev = list(cal.walk("VEVENT"))[0]
    assert ev.get("dtend").dt == datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC)


def test_generate_calendar_ics_optional_fields(tz_utc):
    e = _FakeEvent(
        "d@test", datetime(2026, 1, 1, 10, 0, 0),
        dtend=datetime(2026, 1, 1, 11, 0, 0),
        summary="D", description="Desc", location="Loc", color="#ABCDEF",
    )
    out = generate_calendar_ics([e])
    cal = Calendar.from_ical(out)
    ev = list(cal.walk("VEVENT"))[0]
    assert str(ev.get("summary")) == "D"
    assert str(ev.get("description")) == "Desc"
    assert str(ev.get("location")) == "Loc"
    assert str(ev.get("X-APPLE-CALENDAR-COLOR")) == "#ABCDEF"


def test_generate_calendar_ics_emits_tzid_and_x_wr_timezone(monkeypatch):
    monkeypatch.setattr(settings, "default_timezone", "Australia/Brisbane")
    # Event has no per-event tz, so falls back to server default (Brisbane).
    # Stored dt is naive UTC 10:00 -> 20:00 Brisbane wall-clock.
    e = _FakeEvent("tz@test", datetime(2026, 1, 1, 10, 0, 0), summary="TZ")
    out = generate_calendar_ics([e])
    assert "X-WR-TIMEZONE:Australia/Brisbane" in out
    assert "DTSTART;TZID=Australia/Brisbane:20260101T200000" in out
    assert "BEGIN:VTIMEZONE" in out
    assert "TZID:Australia/Brisbane" in out


def test_generate_calendar_ics_uses_per_event_timezone(tz_utc):
    # Server default is UTC but event carries its own tz; per-event tz wins.
    e = _FakeEvent(
        "pet@test", datetime(2026, 1, 1, 10, 0, 0),
        summary="PET", timezone="Australia/Brisbane",
    )
    out = generate_calendar_ics([e])
    # 10:00 UTC -> 20:00 Brisbane
    assert "DTSTART;TZID=Australia/Brisbane:20260101T200000" in out


def test_generate_calendar_ics_legacy_event_no_timezone_uses_default(tz_utc):
    # Pre-migration events have timezone=NULL; must fall back to server default.
    e = _FakeEvent("leg@test", datetime(2026, 1, 1, 10, 0, 0), summary="LEG", timezone=None)
    out = generate_calendar_ics([e])
    # UTC default -> Z suffix, no TZID param
    assert "DTSTART:20260101T100000Z" in out


# ---------- extra branch coverage ----------

def test_parse_ics_all_day_with_dtend_combined():
    # all-day DTEND (date) is combined to midnight datetime (ics_parser.py:44)
    ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:ad2@test
SUMMARY:TwoDay
DTSTART;VALUE=DATE:20260101
DTEND;VALUE=DATE:20260103
END:VEVENT
END:VCALENDAR
"""
    _, _, _, dtstart, dtend, _, _, _, _ = parse_ics(ics)
    assert dtstart == datetime(2026, 1, 1, 0, 0, 0)
    assert dtend == datetime(2026, 1, 3, 0, 0, 0)


def test_parse_ics_bulk_full_event_all_fields():
    # exercises the description/dtend(all-day)/location/rrule/color branches in bulk
    ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:full@t
SUMMARY:Full
DESCRIPTION:Bulk desc
LOCATION:HQ
DTSTART;VALUE=DATE:20260101
DTEND;VALUE=DATE:20260102
RRULE:FREQ=DAILY
X-APPLE-CALENDAR-COLOR:#AABBCC
END:VEVENT
END:VCALENDAR
"""
    events = parse_ics_bulk(ics)
    assert len(events) == 1
    e = events[0]
    assert e["summary"] == "Full"
    assert e["description"] == "Bulk desc"
    assert e["location"] == "HQ"
    assert e["dtstart"] == datetime(2026, 1, 1, 0, 0, 0)
    assert e["dtend"] == datetime(2026, 1, 2, 0, 0, 0)
    assert e["is_all_day"] is True
    assert e["color"] == "#AABBCC"
    # all-day VALUE=DATE carries no TZID
    assert e["timezone"] is None
    # rrule: comes back as vRecur repr (QUIRK, same as parse_ics)
    assert e["rrule"].startswith("vRecur(")


def test_parse_ics_bulk_missing_dtstart_defaults_to_utcnow():
    ics = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:nots@t
SUMMARY:NoDt
END:VEVENT
END:VCALENDAR
"""
    before = datetime.utcnow()
    events = parse_ics_bulk(ics)
    after = datetime.utcnow()
    assert len(events) == 1
    assert before <= events[0]["dtstart"] <= after


def test_parse_rrule_string_invalid_until_falls_back_to_string():
    # malformed UNTIL -> except ValueError -> raw string (ics_parser.py:173-174)
    result = parse_rrule_string("UNTIL=not-a-date")
    assert result == {"until": "not-a-date"}


def test_generate_calendar_ics_includes_event_rrule(tz_utc):
    # exercises the rrule branch in generate_calendar_ics (ics_parser.py:297-300)
    e = _FakeEvent(
        "r@test", datetime(2026, 1, 1, 10, 0, 0),
        dtend=datetime(2026, 1, 1, 11, 0, 0),
        summary="R", rrule="FREQ=DAILY;INTERVAL=2",
    )
    out = generate_calendar_ics([e])
    cal = Calendar.from_ical(out)
    ev = list(cal.walk("VEVENT"))[0]
    assert ev.get("rrule") is not None
