from icalendar import Calendar, Event as ICalEvent, vDate, vDatetime
from datetime import datetime, timedelta, date, timezone
from typing import Optional, Tuple
from dateutil import parser as date_parser
import uuid


def ensure_utc_naive(dt: datetime) -> datetime:
    """Convert datetime to UTC and strip timezone info for database storage"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def parse_ics(ics_content: str) -> Tuple[str, Optional[str], Optional[str], datetime, Optional[datetime], Optional[str], Optional[str]]:
    cal = Calendar.from_ical(ics_content)
    
    uid = str(uuid.uuid4())
    summary = None
    description = None
    dtstart = None
    dtend = None
    location = None
    rrule = None
    
    for component in cal.walk():
        if component.name == "VEVENT":
            if component.get("uid"):
                uid = str(component.get("uid"))
            if component.get("summary"):
                summary = str(component.get("summary"))
            if component.get("description"):
                description = str(component.get("description"))
            if component.get("dtstart"):
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
            break
    
    if dtstart is None:
        dtstart = datetime.utcnow()
    
    return uid, summary, description, dtstart, dtend, location, rrule


def parse_rrule_string(rrule_str: str) -> dict:
    """Parse an RRULE string like 'FREQ=WEEKLY;INTERVAL=2' into a dict"""
    if not rrule_str:
        return {}
    
    # Strip RRULE: prefix if present
    if rrule_str.upper().startswith('RRULE:'):
        rrule_str = rrule_str[6:]
    
    result = {}
    parts = rrule_str.split(';')
    
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            key = key.strip().upper()
            value = value.strip()
            
            # Convert numeric values
            if key in ['INTERVAL', 'COUNT', 'BYMONTH', 'BYMONTHDAY', 'BYYEARDAY', 'BYWEEKNO', 'BYHOUR', 'BYMINUTE', 'BYSECOND']:
                try:
                    result[key.lower()] = int(value)
                except ValueError:
                    result[key.lower()] = value
            elif key == 'UNTIL':
                # Parse UNTIL date
                try:
                    if len(value) == 8:
                        result[key.lower()] = datetime.strptime(value, '%Y%m%d').date()
                    else:
                        result[key.lower()] = datetime.strptime(value.replace('Z', ''), '%Y%m%dT%H%M%S')
                except ValueError:
                    result[key.lower()] = value
            elif key == 'BYDAY':
                # BYDAY can have multiple values
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
) -> str:
    cal = Calendar()
    cal.add("prodid", "-//KalenDAV Server//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    
    event = ICalEvent()
    event.add("uid", uid)
    
    if is_all_day:
        start_date = dtstart.date() if isinstance(dtstart, datetime) else dtstart
        event.add("dtstart", vDate(start_date))
        if dtend:
            end_date = dtend.date() if isinstance(dtend, datetime) else dtend
            event.add("dtend", vDate(end_date))
    else:
        event.add("dtstart", dtstart)
        if dtend:
            event.add("dtend", dtend)
        else:
            event.add("dtend", dtstart + timedelta(hours=1))
    
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


def generate_calendar_ics(events: list, calendar_name: str = "Calendar") -> str:
    cal = Calendar()
    cal.add("prodid", "-//KalenDAV Server//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", calendar_name)
    
    for event in events:
        ical_event = ICalEvent()
        ical_event.add("uid", event.uid)
        ical_event.add("dtstart", event.dtstart)
        if event.dtend:
            ical_event.add("dtend", event.dtend)
        else:
            ical_event.add("dtend", event.dtstart + timedelta(hours=1))
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
        
        cal.add_component(ical_event)
    
    return cal.to_ical().decode("utf-8")
