from icalendar import Calendar, Event as ICalEvent, vDate, vDatetime
from datetime import datetime, timedelta, date
from typing import Optional, Tuple
from dateutil import parser as date_parser
import uuid


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
            if component.get("dtend"):
                dtend = component.get("dtend").dt
                if not isinstance(dtend, datetime):
                    dtend = datetime.combine(dtend, datetime.min.time())
            if component.get("location"):
                location = str(component.get("location"))
            if component.get("rrule"):
                rrule = str(component.get("rrule"))
            break
    
    if dtstart is None:
        dtstart = datetime.utcnow()
    
    return uid, summary, description, dtstart, dtend, location, rrule


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
        from icalendar import vRecur
        event.add("rrule", vRecur.from_ical(rrule))
    
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
        
        cal.add_component(ical_event)
    
    return cal.to_ical().decode("utf-8")
