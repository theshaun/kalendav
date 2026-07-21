from lxml import etree
from datetime import datetime
from typing import Optional, Iterable
import hashlib
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


def add_sync_token(multistatus: etree.Element, token: str) -> None:
    """Attach <d:sync-token> as a direct child of <d:multistatus>.

    Required by RFC 6578 §3.4 on sync-collection REPORT responses; some clients
    (e.g. the .NET Dav.Client) call .Single() on it and crash with
    InvalidOperationException if absent.
    """
    token_elem = etree.SubElement(multistatus, f"{D}sync-token")
    token_elem.text = token


def compute_sync_token(calendar_id: int, events: Iterable) -> str:
    """Opaque token that changes whenever the calendar's event set changes.

    Hashes sorted (uid, updated_at) tuples so adds, updates, and deletes all
    advance the token. Empty calendar yields a stable zero-state token.
    Uses isoformat (microsecond precision) so rapid successive edits produce
    distinct tokens.
    """
    items = sorted(
        (e.uid, (e.updated_at or e.created_at).isoformat())
        for e in events
    )
    state = "|".join(f"{u}@{t}" for u, t in items)
    digest = hashlib.sha256(state.encode()).hexdigest()[:16]
    return f"{settings.base_uri}/sync/cal{calendar_id}/{digest}"


def add_principal_response(parent: etree.Element, href: str, principal_url: str) -> etree.Element:
    response = add_response(parent, href)
    prop = add_propstat(response)
    
    resourcetype = etree.SubElement(prop, f"{D}resourcetype")
    etree.SubElement(resourcetype, f"{D}collection")
    
    displayname = etree.SubElement(prop, f"{D}displayname")
    displayname.text = "Calendar"
    
    calendar_color = etree.SubElement(prop, f"{ICAL}calendar-color")
    calendar_color.text = "#3B82F6"
    
    current_user_principal = etree.SubElement(prop, f"{D}current-user-principal")
    href_elem = etree.SubElement(current_user_principal, f"{D}href")
    href_elem.text = principal_url
    
    principal_url_elem = etree.SubElement(prop, f"{D}principal-URL")
    href_elem2 = etree.SubElement(principal_url_elem, f"{D}href")
    href_elem2.text = principal_url
    
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
    sync_token: Optional[str] = None,
    writable: bool = True,
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

    # getctag and sync-token must stay in sync: clients compare getctag (or
    # sync-token) between polls to decide whether to re-sync.
    token = sync_token or f"{settings.base_uri}/sync/cal{calendar_id}/empty"
    getctag = etree.SubElement(prop, f"{CS}getctag")
    getctag.text = token

    cal_sync_token = etree.SubElement(prop, f"{D}sync-token")
    cal_sync_token.text = token

    # RFC 3744 §4.3 — current-user-privilege-set tells the client what
    # operations the authenticated user may perform.  KashCal (and other
    # strict clients) treats a missing privilege set as read-only.
    privilege_set = etree.SubElement(prop, f"{D}current-user-privilege-set")
    for priv in ("read", "read-current-user-privilege-set", "read-acl"):
        etree.SubElement(privilege_set, f"{D}{priv}")
    if writable:
        for priv in ("write", "write-content", "write-properties", "bind", "unbind"):
            etree.SubElement(privilege_set, f"{D}{priv}")

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


def build_well_known_caldav(base_url: str) -> str:
    """RFC 6764 §3.3 — 207 Multi-Status with calendar-home-set for service discovery."""
    multistatus = create_multistatus()
    response = add_response(multistatus, f"{base_url}/dav/")
    prop = add_propstat(response)

    calendar_home_set = etree.SubElement(prop, f"{C}calendar-home-set")
    href_elem = etree.SubElement(calendar_home_set, f"{D}href")
    href_elem.text = f"{base_url}/dav/"

    return xml_to_string(multistatus)


def xml_to_string(element: etree.Element) -> str:
    return etree.tostring(element, xml_declaration=True, encoding="UTF-8", pretty_print=True).decode("utf-8")
