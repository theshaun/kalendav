from lxml import etree
from datetime import datetime
from typing import Optional
from app.config import settings


NSMAP = {
    "d": "DAV:",
    "c": "urn:ietf:params:xml:ns:caldav",
    "cs": "http://calendarserver.org/ns/",
    "ical": "http://apple.com/ns/ical/",
}

D = "{DAV:}"
C = "{urn:ietf:params:xml:ns:caldav}"
CS = "{http://calendarserver.org/ns/}"
ICAL = "{http://apple.com/ns/ical/}"


def create_multistatus() -> etree.Element:
    return etree.Element(f"{D}multistatus", nsmap=NSMAP)


def add_response(parent: etree.Element, href: str) -> etree.Element:
    response = etree.SubElement(parent, f"{D}response")
    href_elem = etree.SubElement(response, f"{D}href")
    href_elem.text = href
    return response


def add_propstat(response: etree.Element, status: str = "HTTP/1.1 200 OK") -> etree.Element:
    propstat = etree.SubElement(response, f"{D}propstat")
    prop = etree.SubElement(propstat, f"{D}prop")
    status_elem = etree.SubElement(propstat, f"{D}status")
    status_elem.text = status
    return prop


def add_principal_response(parent: etree.Element, href: str, principal_url: str) -> etree.Element:
    response = add_response(parent, href)
    prop = add_propstat(response)
    
    resourcetype = etree.SubElement(prop, f"{D}resourcetype")
    etree.SubElement(resourcetype, f"{D}collection")
    etree.SubElement(resourcetype, f"{C}calendar")
    
    displayname = etree.SubElement(prop, f"{D}displayname")
    displayname.text = "Calendar"
    
    calendar_color = etree.SubElement(prop, f"{ICAL}calendar-color")
    calendar_color.text = "#3B82F6"
    
    principal_url_elem = etree.SubElement(prop, f"{D}principal-URL")
    href_elem = etree.SubElement(principal_url_elem, f"{D}href")
    href_elem.text = principal_url
    
    calendar_home_set = etree.SubElement(prop, f"{C}calendar-home-set")
    href_elem2 = etree.SubElement(calendar_home_set, f"{D}href")
    href_elem2.text = f"{principal_url}/calendars/"
    
    return response


def add_calendar_response(
    parent: etree.Element,
    href: str,
    calendar_id: int,
    name: str,
    description: Optional[str] = None,
    color: str = "#3B82F6",
) -> etree.Element:
    response = add_response(parent, href)
    prop = add_propstat(response)
    
    resourcetype = etree.SubElement(prop, f"{D}resourcetype")
    etree.SubElement(resourcetype, f"{D}collection")
    etree.SubElement(resourcetype, f"{C}calendar")
    
    displayname = etree.SubElement(prop, f"{D}displayname")
    displayname.text = name
    
    if description:
        desc = etree.SubElement(prop, f"{D}description")
        desc.text = description
    
    calendar_color = etree.SubElement(prop, f"{ICAL}calendar-color")
    calendar_color.text = color
    
    supported_calendar_component = etree.SubElement(prop, f"{C}supported-calendar-component-set")
    comp = etree.SubElement(supported_calendar_component, f"{C}comp")
    comp.set("name", "VEVENT")
    
    getctag = etree.SubElement(prop, f"{CS}getctag")
    getctag.text = f"calendar-{calendar_id}-1"
    
    sync_token = etree.SubElement(prop, f"{D}sync-token")
    sync_token.text = f"{settings.base_uri}/sync/calendar-{calendar_id}-1"
    
    return response


def add_event_response(
    parent: etree.Element,
    href: str,
    uid: str,
    summary: str,
    dtstart: datetime,
    dtend: Optional[datetime],
    etag: str,
    raw_ics: str,
) -> etree.Element:
    response = add_response(parent, href)
    prop = add_propstat(response)
    
    displayname = etree.SubElement(prop, f"{D}displayname")
    displayname.text = summary or uid
    
    getetag = etree.SubElement(prop, f"{D}getetag")
    getetag.text = etag
    
    getcontenttype = etree.SubElement(prop, f"{D}getcontenttype")
    getcontenttype.text = "text/calendar; charset=utf-8"
    
    resourcetype = etree.SubElement(prop, f"{D}resourcetype")
    
    calendar_data = etree.SubElement(prop, f"{C}calendar-data")
    calendar_data.text = raw_ics
    
    return response


def xml_to_string(element: etree.Element) -> str:
    return etree.tostring(element, xml_declaration=True, encoding="UTF-8", pretty_print=True).decode("utf-8")
