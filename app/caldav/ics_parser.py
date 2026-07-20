from icalendar import Calendar, Event as ICalEvent, Timezone as ICalTimezone, vDate, vDatetime
from datetime import datetime, timedelta, date, timezone
from typing import Optional, Tuple, List, Dict
from dateutil import parser as date_parser
from zoneinfo import ZoneInfo
import uuid

from app.config import settings


def ensure_utc_naive(dt: datetime) -> datetime:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _resolve_tz(tz_name: Optional[str]) -> ZoneInfo:
    # Unknown / missing -> server default rather than raising.
    if not tz_name:
        return settings.tz
    try:
        return ZoneInfo(tz_name)
    except (KeyError, Exception):
        return settings.tz


def convert_utc_to_tz(dt: Optional[datetime], tz_name: Optional[str]) -> Optional[datetime]:
    """Convert a naive UTC datetime to an aware datetime in the target tz.

    Stored events are naive UTC. This shifts the wall-clock to the target
    timezone so icalendar emits ``DTSTART;TZID=<tz>:<local-wall-clock>``.
    Aware datetimes pass through unchanged.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    target_tz = _resolve_tz(tz_name)
    return dt.replace(tzinfo=timezone.utc).astimezone(target_tz)


def extract_tzid(component) -> Optional[str]:
    """Pull the original TZID off a VEVENT's DTSTART, if any.

    Returns ``"UTC"`` when DTSTART carried a trailing ``Z`` (UTC indicator),
    the IANA name when a ``TZID`` parameter was present, or ``None`` for
    floating times.
    """
    dtstart_prop = component.get("dtstart")
    if dtstart_prop is None:
        return None
    try:
        tzid = dtstart_prop.params.get("TZID")
        if tzid:
            return str(tzid)
    except Exception:
        pass
    dt = dtstart_prop.dt
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        return "UTC"
    return None


def _add_vtimezone(cal: Calendar, tz_name: str) -> None:
    # UTC is implicit in RFC 5545 (Z suffix); skip to avoid bloating the feed.
    if not tz_name or tz_name == "UTC":
        return
    try:
        cal.add_component(ICalTimezone.from_tzinfo(ZoneInfo(tz_name), tzid=tz_name))
    except Exception:
        # VTIMEZONE is best-effort; a missing block is still valid ICS,
        # just less friendly to clients that need offset transitions.
        pass


def _add_vtimezone_if_needed(cal: Calendar) -> None:
    """Attach a VTIMEZONE component for the server default timezone."""
    _add_vtimezone(cal, settings.default_timezone)


def parse_ics(ics_content: str) -> Tuple[str, Optional[str], Optional[str], datetime, Optional[datetime], Optional[str], Optional[str], Optional[str], Optional[str]]:
    cal = Calendar.from_ical(ics_content)

    uid = str(uuid.uuid4())
    summary = None
    description = None
    dtstart = None
    dtend = None
    location = None
    rrule = None
    color = None
    event_tz = None

    for component in cal.walk():
        if component.name == "VEVENT":
            if component.get("uid"):
                uid = str(component.get("uid"))
            if component.get("summary"):
                summary = str(component.get("summary"))
            if component.get("description"):
                description = str(component.get("description"))
            if component.get("dtstart"):
                event_tz = extract_tzid(component)
                dtstart = component.get("dtstart").dt
                if not isinstance(dtstart, datetime):
                    dtstart = datetime.combine(dtstart, datetime.min.time())
                dtstart = ensure_utc_naive(dtstart)
            if component.get("dtend"):
                dtend = component.get("dtend").dt
                if not isinstance(dtend, datetime):
                    dtend = datetime.combine(dtend, datetime.min.time())
                dtend = ensure_utc_naive(dtend)
            if component.get("location"):
                location = str(component.get("location"))
            if component.get("rrule"):
                rrule_raw = str(component.get("rrule"))
                if rrule_raw.upper().startswith('RRULE:'):
                    rrule = rrule_raw[6:]
                else:
                    rrule = rrule_raw
            x_color = component.get("X-APPLE-CALENDAR-COLOR")
            if x_color:
                color = str(x_color)
            break

    if dtstart is None:
        dtstart = datetime.utcnow()

    return uid, summary, description, dtstart, dtend, location, rrule, color, event_tz


def parse_ics_bulk(ics_content: str) -> List[Dict]:
    cal = Calendar.from_ical(ics_content)
    events = []

    for component in cal.walk():
        if component.name == "VEVENT":
            uid = str(uuid.uuid4())
            summary = None
            description = None
            dtstart = None
            dtend = None
            location = None
            rrule = None
            color = None
            event_tz = None

            if component.get("uid"):
                uid = str(component.get("uid"))
            if component.get("summary"):
                summary = str(component.get("summary"))
            if component.get("description"):
                description = str(component.get("description"))
            if component.get("dtstart"):
                event_tz = extract_tzid(component)
                dtstart = component.get("dtstart").dt
                if not isinstance(dtstart, datetime):
                    dtstart = datetime.combine(dtstart, datetime.min.time())
                dtstart = ensure_utc_naive(dtstart)
            if component.get("dtend"):
                dtend = component.get("dtend").dt
                if not isinstance(dtend, datetime):
                    dtend = datetime.combine(dtend, datetime.min.time())
                dtend = ensure_utc_naive(dtend)
            if component.get("location"):
                location = str(component.get("location"))
            if component.get("rrule"):
                rrule_raw = str(component.get("rrule"))
                if rrule_raw.upper().startswith('RRULE:'):
                    rrule = rrule_raw[6:]
                else:
                    rrule = rrule_raw
            x_color = component.get("X-APPLE-CALENDAR-COLOR")
            if x_color:
                color = str(x_color)

            if dtstart is None:
                dtstart = datetime.utcnow()

            is_all_day = False
            if component.get("dtstart"):
                original_dt = component.get("dtstart").dt
                if isinstance(original_dt, date) and not isinstance(original_dt, datetime):
                    is_all_day = True

            new_uid = str(uuid.uuid4())
            raw_ics = generate_ics(
                uid=new_uid,
                summary=summary or "",
                dtstart=dtstart,
                dtend=dtend,
                description=description,
                location=location,
                rrule=rrule,
                is_all_day=is_all_day,
                color=color,
                timezone=event_tz,
            )

            events.append({
                "uid": new_uid,
                "summary": summary,
                "description": description,
                "dtstart": dtstart,
                "dtend": dtend,
                "location": location,
                "rrule": rrule,
                "color": color,
                "timezone": event_tz,
                "is_all_day": is_all_day,
                "raw_ics": raw_ics,
            })

    return events


def parse_rrule_string(rrule_str: str) -> dict:
    if not rrule_str:
        return {}
    
    if rrule_str.upper().startswith('RRULE:'):
        rrule_str = rrule_str[6:]
    
    result = {}
    parts = rrule_str.split(';')
    
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            key = key.strip().upper()
            value = value.strip()
            
            if key in ['INTERVAL', 'COUNT', 'BYMONTH', 'BYMONTHDAY', 'BYYEARDAY', 'BYWEEKNO', 'BYHOUR', 'BYMINUTE', 'BYSECOND']:
                try:
                    result[key.lower()] = int(value)
                except ValueError:
                    result[key.lower()] = value
            elif key == 'UNTIL':
                try:
                    if len(value) == 8:
                        result[key.lower()] = datetime.strptime(value, '%Y%m%d').date()
                    else:
                        result[key.lower()] = datetime.strptime(value.replace('Z', ''), '%Y%m%dT%H%M%S')
                except ValueError:
                    result[key.lower()] = value
            elif key == 'BYDAY':
                result[key.lower()] = [v.strip() for v in value.split(',')]
            else:
                result[key.lower()] = value
    
    return result


def generate_ics(
    uid: str,
    summary: str,
    dtstart: datetime,
    dtend: Optional[datetime] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    rrule: Optional[str] = None,
    is_all_day: bool = False,
    color: Optional[str] = None,
    timezone: Optional[str] = None,
) -> str:
    effective_tz = timezone or settings.default_timezone
    cal = Calendar()
    cal.add("prodid", "-//KalenDAV Server//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-timezone", effective_tz)
    _add_vtimezone(cal, effective_tz)

    event = ICalEvent()
    event.add("uid", uid)

    if is_all_day:
        start_date = dtstart.date() if isinstance(dtstart, datetime) else dtstart
        event.add("dtstart", vDate(start_date))
        if dtend:
            end_date = dtend.date() if isinstance(dtend, datetime) else dtend
            event.add("dtend", vDate(end_date))
    else:
        localized_start = convert_utc_to_tz(dtstart, timezone)
        event.add("dtstart", localized_start)
        if dtend:
            event.add("dtend", convert_utc_to_tz(dtend, timezone))
        else:
            event.add("dtend", localized_start + timedelta(hours=1))

    event.add("dtstamp", datetime.utcnow())
    event.add("summary", summary)

    if description:
        event.add("description", description)
    if location:
        event.add("location", location)
    if rrule:
        rrule_dict = parse_rrule_string(rrule)
        if rrule_dict:
            event.add("rrule", rrule_dict)
    if color:
        event.add("X-APPLE-CALENDAR-COLOR", color)

    cal.add_component(event)

    return cal.to_ical().decode("utf-8")


def build_rrule(
    freq: str,
    interval: int = 1,
    count: Optional[int] = None,
    until: Optional[datetime] = None,
    byday: Optional[list] = None,
) -> Optional[str]:
    if freq == "none":
        return None
    
    freq_map = {
        "daily": "DAILY",
        "weekly": "WEEKLY",
        "monthly": "MONTHLY",
        "yearly": "YEARLY",
    }
    
    freq_val = freq_map.get(freq.lower())
    if not freq_val:
        return None
    
    parts = [f"FREQ={freq_val}"]
    
    if interval > 1:
        parts.append(f"INTERVAL={interval}")
    
    if count:
        parts.append(f"COUNT={count}")
    elif until:
        parts.append(f"UNTIL={until.strftime('%Y%m%dT%H%M%SZ')}")
    
    if byday and freq.lower() == "weekly":
        parts.append(f"BYDAY={','.join(byday)}")
    
    return ";".join(parts)


def generate_calendar_ics(events: list, calendar_name: str = "Calendar", calendar_color: Optional[str] = None) -> str:
    cal = Calendar()
    cal.add("prodid", "-//KalenDAV Server//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", calendar_name)
    cal.add("x-wr-timezone", settings.default_timezone)
    _add_vtimezone(cal, settings.default_timezone)

    # Emit VTIMEZONE for every unique tz appearing in the event set, not just
    # the server default. Clients with stale tzdata (older Android, some iOS
    # configs) need the offset/rule definition inline or they misrender.
    seen_tzs = {settings.default_timezone}
    for event in events:
        event_tz = getattr(event, "timezone", None)
        if event_tz and event_tz not in seen_tzs:
            _add_vtimezone(cal, event_tz)
            seen_tzs.add(event_tz)

    if calendar_color:
        cal.add("x-apple-calendar-color", calendar_color)

    for event in events:
        event_tz = getattr(event, "timezone", None)
        is_all_day = bool(getattr(event, "is_all_day", False))
        ical_event = ICalEvent()
        ical_event.add("uid", event.uid)

        if is_all_day:
            # RFC 5545 §3.3.4: all-day events use VALUE=DATE — no time, no tz.
            start_date = event.dtstart.date() if isinstance(event.dtstart, datetime) else event.dtstart
            ical_event.add("dtstart", start_date, {"value": "DATE"})
            if event.dtend:
                end_date = event.dtend.date() if isinstance(event.dtend, datetime) else event.dtend
                ical_event.add("dtend", end_date, {"value": "DATE"})
            else:
                ical_event.add("dtend", start_date + timedelta(days=1), {"value": "DATE"})
        else:
            localized_start = convert_utc_to_tz(event.dtstart, event_tz)
            ical_event.add("dtstart", localized_start)
            if event.dtend:
                ical_event.add("dtend", convert_utc_to_tz(event.dtend, event_tz))
            else:
                ical_event.add("dtend", localized_start + timedelta(hours=1))
        ical_event.add("dtstamp", datetime.utcnow())
        if event.summary:
            ical_event.add("summary", event.summary)
        if event.description:
            ical_event.add("description", event.description)
        if event.location:
            ical_event.add("location", event.location)
        if event.rrule:
            rrule_dict = parse_rrule_string(event.rrule)
            if rrule_dict:
                ical_event.add("rrule", rrule_dict)
        if event.color:
            ical_event.add("X-APPLE-CALENDAR-COLOR", event.color)

        cal.add_component(ical_event)

    return cal.to_ical().decode("utf-8")
