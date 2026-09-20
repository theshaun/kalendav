from fastapi import APIRouter, Request, Response, Depends, HTTPException, status
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from lxml import etree
from app.database import get_db
from app.models import User, Calendar, Event, CalendarShare, Task
from app.auth import get_current_user
from app.services.task_service import TaskService
from app.caldav.xml_responses import (
    create_multistatus,
    add_response,
    add_propstat,
    add_principal_response,
    add_calendar_response,
    add_event_response,
    add_sync_token,
    compute_sync_token,
    xml_to_string,
)
from app.caldav.ics_parser import (
    parse_ics,
    generate_ics,
    parse_vtodo,
    generate_vtodo,
    detect_component,
)
from datetime import datetime
import hashlib
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.api_route("/", methods=["OPTIONS"])
@router.api_route("/{path:path}", methods=["OPTIONS"])
async def handle_options(request: Request, path: str = ""):
    return Response(
        status_code=200,
        headers={
            "DAV": "1, 2, 3, calendar-access, calendar-schedule",
            "Allow": "OPTIONS, PROPFIND, PROPPATCH, GET, PUT, DELETE, REPORT, MKCALENDAR",
            "Content-Length": "0",
        },
    )


def check_calendar_permission(user: User, calendar: Calendar, require_write: bool = False) -> bool:
    if calendar.user_id == user.id:
        return True
    
    for share in calendar.shares:
        if share.user_id == user.id:
            if require_write:
                return share.permission.value in ["write", "admin"]
            return True
    
    return False


async def get_calendar_with_permission(
    calendar_id: int,
    user: User,
    db: AsyncSession,
    require_write: bool = False,
) -> Optional[Calendar]:
    result = await db.execute(
        select(Calendar)
        .options(selectinload(Calendar.shares))
        .where(Calendar.id == calendar_id)
    )
    calendar = result.scalar_one_or_none()
    
    if not calendar:
        return None
    
    if not check_calendar_permission(user, calendar, require_write):
        return None
    
    return calendar


@router.api_route("/", methods=["PROPFIND", "PROPPATCH", "MKCALENDAR"])
@router.api_route("/{path:path}", methods=["PROPFIND", "PROPPATCH", "MKCALENDAR"])
async def caldav_webdav(
    request: Request,
    path: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    method = request.method
    path_parts = [p for p in path.split("/") if p]
    
    if method == "PROPFIND":
        return await handle_propfind(request, path_parts, user, db)
    elif method == "PROPPATCH":
        return await handle_proppatch(request, path_parts, user, db)
    elif method == "MKCALENDAR":
        return await handle_mkcalendar(request, path_parts, user, db)
    
    raise HTTPException(status_code=405)


@router.api_route("/", methods=["GET", "PUT", "DELETE", "REPORT"])
@router.api_route("/{path:path}", methods=["GET", "PUT", "DELETE", "REPORT"])
async def caldav_resources(
    request: Request,
    path: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    method = request.method
    path_parts = [p for p in path.split("/") if p]
    
    if method == "GET":
        return await handle_get(path_parts, user, db)
    elif method == "PUT":
        body = await request.body()
        return await handle_put(path_parts, body, user, db)
    elif method == "DELETE":
        return await handle_delete(path_parts, user, db)
    elif method == "REPORT":
        body = await request.body()
        return await handle_report(request, path_parts, body, user, db)
    
    raise HTTPException(status_code=405)


async def handle_propfind(request: Request, path_parts: list, user: User, db: AsyncSession):
    body = await request.body()
    depth = request.headers.get("Depth", "0")
    
    multistatus = create_multistatus()
    
    if len(path_parts) == 0:
        add_principal_response(multistatus, "/dav/", f"/dav/principals/{user.username}/")
    
    elif len(path_parts) == 1 and path_parts[0] == "principals":
        add_response(multistatus, f"/dav/principals/{user.username}/")
    
    elif len(path_parts) >= 3 and path_parts[0] == "principals" and path_parts[2] == "calendars":
        result = await db.execute(
            select(Calendar)
            .options(
                selectinload(Calendar.shares),
                selectinload(Calendar.events),
                selectinload(Calendar.tasks),
            )
            .where(Calendar.user_id == user.id)
        )
        owned_calendars = result.scalars().all()

        result = await db.execute(
            select(CalendarShare)
            .options(
                selectinload(CalendarShare.calendar).selectinload(Calendar.events),
                selectinload(CalendarShare.calendar).selectinload(Calendar.tasks),
            )
            .where(CalendarShare.user_id == user.id)
        )
        shared = result.scalars().all()
        shared_calendars = [s.calendar for s in shared]

        all_calendars = list(owned_calendars) + shared_calendars

        write_share_ids = {s.calendar_id for s in shared if s.permission.value in ("write", "admin")}
        writable_map = {c.id: True for c in owned_calendars}
        for c in shared_calendars:
            writable_map.setdefault(c.id, c.id in write_share_ids)

        if depth == "1":
            add_response(multistatus, f"/dav/principals/{user.username}/calendars/")

        for cal in all_calendars:
            href = f"/dav/{user.username}/calendars/{cal.id}/"
            # B2 fix: include Tasks so the calendar-collection token advances on task writes too.
            add_calendar_response(
                multistatus,
                href,
                cal.id,
                cal.name,
                cal.description,
                cal.color or "#3B82F6",
                sync_token=compute_sync_token(cal.id, list(cal.events) + list(cal.tasks)),
                writable=writable_map.get(cal.id, True),
            )
    
    elif len(path_parts) >= 2 and path_parts[0] == "principals":
        add_principal_response(
            multistatus,
            f"/dav/principals/{user.username}/",
            f"/dav/principals/{user.username}/",
        )
    
    elif len(path_parts) >= 3 and path_parts[1] == "calendars":
        try:
            cal_id = int(path_parts[2])
        except ValueError:
            raise HTTPException(status_code=404)

        calendar = await get_calendar_with_permission(cal_id, user, db)
        if not calendar:
            raise HTTPException(status_code=404)

        is_writable = calendar.user_id == user.id or check_calendar_permission(
            user, calendar, require_write=True
        )

        result = await db.execute(
            select(Event).where(Event.calendar_id == calendar.id)
        )
        events_for_token = result.scalars().all()

        tasks_result = await db.execute(
            select(Task).where(Task.calendar_id == calendar.id)
        )
        tasks_for_token = tasks_result.scalars().all()

        # B2 fix: token must cover Tasks too, else polling clients never re-sync.
        add_calendar_response(
            multistatus,
            f"/dav/{user.username}/calendars/{cal_id}/",
            calendar.id,
            calendar.name,
            calendar.description,
            calendar.color or "#3B82F6",
            sync_token=compute_sync_token(calendar.id, list(events_for_token) + list(tasks_for_token)),
            writable=is_writable,
        )

        if depth == "1":
            for event in events_for_token:
                href = f"/dav/{user.username}/calendars/{cal_id}/{event.uid}.ics"
                etag = hashlib.md5(event.raw_ics.encode()).hexdigest()
                add_event_response(
                    multistatus,
                    href,
                    event.uid,
                    event.summary or event.uid,
                    event.dtstart,
                    event.dtend,
                    etag,
                    event.raw_ics,
                )
            for task in tasks_for_token:
                href = f"/dav/{user.username}/calendars/{cal_id}/{task.uid}.ics"
                etag = hashlib.md5(task.raw_ics.encode()).hexdigest()
                add_event_response(
                    multistatus,
                    href,
                    task.uid,
                    task.summary or task.uid,
                    None,
                    None,
                    etag,
                    task.raw_ics,
                )
    
    elif len(path_parts) >= 2 and path_parts[1] == "calendars":
        result = await db.execute(
            select(Calendar)
            .options(
                selectinload(Calendar.shares),
                selectinload(Calendar.events),
                selectinload(Calendar.tasks),
            )
            .where(Calendar.user_id == user.id)
        )
        owned_calendars = result.scalars().all()

        result = await db.execute(
            select(CalendarShare)
            .options(
                selectinload(CalendarShare.calendar).selectinload(Calendar.events),
                selectinload(CalendarShare.calendar).selectinload(Calendar.tasks),
            )
            .where(CalendarShare.user_id == user.id)
        )
        shared = result.scalars().all()
        shared_calendars = [s.calendar for s in shared]

        all_calendars = list(owned_calendars) + shared_calendars

        write_share_ids = {s.calendar_id for s in shared if s.permission.value in ("write", "admin")}
        writable_map = {c.id: True for c in owned_calendars}
        for c in shared_calendars:
            writable_map.setdefault(c.id, c.id in write_share_ids)

        if depth == "1":
            add_response(multistatus, f"/dav/{user.username}/calendars/")

        for cal in all_calendars:
            href = f"/dav/{user.username}/calendars/{cal.id}/"
            # B2 fix: include Tasks so this token advances on task writes too.
            add_calendar_response(
                multistatus,
                href,
                cal.id,
                cal.name,
                cal.description,
                cal.color or "#3B82F6",
                sync_token=compute_sync_token(cal.id, list(cal.events) + list(cal.tasks)),
                writable=writable_map.get(cal.id, True),
            )
    
    return FastAPIResponse(
        content=xml_to_string(multistatus),
        media_type="application/xml; charset=utf-8",
        status_code=207,
        headers={"DAV": "1, 2, 3, calendar-access, calendar-schedule"},
    )


async def handle_proppatch(request: Request, path_parts: list, user: User, db: AsyncSession):
    if len(path_parts) < 3 or path_parts[1] != "calendars":
        raise HTTPException(status_code=404)
    
    try:
        cal_id = int(path_parts[2])
    except ValueError:
        raise HTTPException(status_code=404)
    
    calendar = await get_calendar_with_permission(cal_id, user, db, require_write=True)
    if not calendar:
        raise HTTPException(status_code=403)
    
    body = await request.body()
    updated_props = []
    
    if body:
        try:
            root = etree.fromstring(body)
            
            ICAL = "{http://apple.com/ns/ical/}"
            D = "{DAV:}"
            
            for set_elem in root.findall(".//{%s}set" % "DAV:"):
                prop_elem = set_elem.find("{%s}prop" % "DAV:")
                if prop_elem is not None:
                    displayname = prop_elem.find(f"{D}displayname")
                    if displayname is not None and displayname.text:
                        calendar.name = displayname.text
                        updated_props.append("displayname")
                    
                    description = prop_elem.find(f"{D}description")
                    if description is not None and description.text:
                        calendar.description = description.text
                        updated_props.append("description")
                    
                    calendar_color = prop_elem.find(f"{ICAL}calendar-color")
                    if calendar_color is not None and calendar_color.text:
                        color_value = calendar_color.text
                        if len(color_value) > 7:
                            color_value = color_value[:7]
                        calendar.color = color_value
                        updated_props.append("calendar-color")
            
            if updated_props:
                await db.commit()
                await db.refresh(calendar)
        except etree.XMLSyntaxError:
            pass
    
    multistatus = create_multistatus()
    response = add_response(multistatus, f"/dav/{user.username}/calendars/{cal_id}/")
    add_propstat(response, "HTTP/1.1 200 OK")
    
    return FastAPIResponse(
        content=xml_to_string(multistatus),
        media_type="application/xml; charset=utf-8",
        status_code=207,
    )


async def handle_mkcalendar(request: Request, path_parts: list, user: User, db: AsyncSession):
    if len(path_parts) < 3 or path_parts[1] != "calendars":
        raise HTTPException(status_code=400)
    
    calendar_name = path_parts[2] if len(path_parts) > 2 else "New Calendar"
    calendar_description = None
    calendar_color = "#3B82F6"
    
    body = await request.body()
    if body:
        try:
            root = etree.fromstring(body)
            
            ICAL = "{http://apple.com/ns/ical/}"
            D = "{DAV:}"
            
            for set_elem in root.findall(".//{%s}set" % "DAV:"):
                prop_elem = set_elem.find("{%s}prop" % "DAV:")
                if prop_elem is not None:
                    displayname = prop_elem.find(f"{D}displayname")
                    if displayname is not None and displayname.text:
                        calendar_name = displayname.text
                    
                    description = prop_elem.find(f"{D}description")
                    if description is not None and description.text:
                        calendar_description = description.text
                    
                    color = prop_elem.find(f"{ICAL}calendar-color")
                    if color is not None and color.text:
                        calendar_color = color.text
        except etree.XMLSyntaxError:
            pass
    
    new_calendar = Calendar(
        user_id=user.id,
        name=calendar_name,
        description=calendar_description,
        color=calendar_color,
    )
    db.add(new_calendar)
    await db.commit()
    await db.refresh(new_calendar)
    
    return Response(status_code=201)


async def handle_get(path_parts: list, user: User, db: AsyncSession):
    logger.info(f"handle_get called with path_parts: {path_parts}")
    
    cal_id = None
    
    # Handle different path patterns
    if len(path_parts) == 1:
        # Pattern: /dav/{uid}.ics - get from default calendar
        uid = path_parts[0].replace(".ics", "")
        
        # Get user's default calendar
        result = await db.execute(
            select(Calendar)
            .where(Calendar.user_id == user.id, Calendar.is_default == True)
        )
        calendar = result.scalar_one_or_none()
        
        if not calendar:
            # Get first calendar if no default
            result = await db.execute(
                select(Calendar)
                .where(Calendar.user_id == user.id)
                .order_by(Calendar.created_at)
            )
            calendar = result.scalars().first()
        
        if not calendar:
            raise HTTPException(status_code=404, detail="No calendar found")
        
        # Single-resource GET: prefer Task, then Event. (B1 fix — previously
        # a Task at this href silently fell through to the merged-calendar path.)
        task_result = await db.execute(
            select(Task).where(Task.calendar_id == calendar.id, Task.uid == uid)
        )
        task = task_result.scalar_one_or_none()
        if task is not None:
            return FastAPIResponse(
                content=task.raw_ics,
                media_type="text/calendar; charset=utf-8",
            )
        
        event_result = await db.execute(
            select(Event).where(Event.calendar_id == calendar.id, Event.uid == uid)
        )
        event = event_result.scalar_one_or_none()
        if event is not None:
            return FastAPIResponse(
                content=event.raw_ics,
                media_type="text/calendar; charset=utf-8",
            )
        
        raise HTTPException(status_code=404, detail="Resource not found")
    
    elif len(path_parts) >= 4 and path_parts[1] == "calendars":
        # Pattern: /dav/{username}/calendars/{calendar_id}/{uid}.ics
        try:
            cal_id = int(path_parts[2])
        except ValueError:
            raise HTTPException(status_code=404)
        
        calendar = await get_calendar_with_permission(cal_id, user, db)
        if not calendar:
            raise HTTPException(status_code=404)
        
        # B1 fix: return the single named resource, not the merged calendar.
        uid = path_parts[3].replace(".ics", "")
        task_result = await db.execute(
            select(Task).where(Task.calendar_id == calendar.id, Task.uid == uid)
        )
        task = task_result.scalar_one_or_none()
        if task is not None:
            return FastAPIResponse(
                content=task.raw_ics,
                media_type="text/calendar; charset=utf-8",
            )

        event_result = await db.execute(
            select(Event).where(Event.calendar_id == calendar.id, Event.uid == uid)
        )
        event = event_result.scalar_one_or_none()
        if event is not None:
            return FastAPIResponse(
                content=event.raw_ics,
                media_type="text/calendar; charset=utf-8",
            )

        raise HTTPException(status_code=404, detail="Resource not found")
    
    else:
        logger.error(f"Invalid path structure for GET: {path_parts}")
        raise HTTPException(status_code=404)


async def handle_put(path_parts: list, body: bytes, user: User, db: AsyncSession):
    logger.info(f"handle_put called with path_parts: {path_parts}")
    
    cal_id = None
    event_uid_from_path = None
    
    # Handle different path patterns
    if len(path_parts) == 1:
        # Pattern: /dav/{event_uid}.ics - use default calendar
        event_uid_from_path = path_parts[0].replace(".ics", "")
        logger.info(f"Direct event PUT for UID: {event_uid_from_path}, using default calendar")
        
        # Get user's default calendar or first calendar
        result = await db.execute(
            select(Calendar)
            .where(Calendar.user_id == user.id)
            .order_by(Calendar.is_default.desc(), Calendar.created_at)
        )
        calendar = result.scalars().first()
        
        if not calendar:
            # Create a default calendar if none exists
            calendar = Calendar(
                user_id=user.id,
                name=f"{user.username}'s Calendar",
                is_default=True,
            )
            db.add(calendar)
            await db.commit()
            await db.refresh(calendar)
            logger.info(f"Created default calendar {calendar.id} for user {user.username}")
    
    elif len(path_parts) >= 4 and path_parts[1] == "calendars":
        # Pattern: /dav/{username}/calendars/{calendar_id}/{event_uid}.ics
        try:
            cal_id = int(path_parts[2])
        except ValueError:
            logger.error(f"Invalid calendar ID in path: {path_parts[2]}")
            raise HTTPException(status_code=404)
        
        calendar = await get_calendar_with_permission(cal_id, user, db, require_write=True)
        if not calendar:
            logger.error(f"No permission for calendar {cal_id} or calendar not found")
            raise HTTPException(status_code=403)
    
    else:
        logger.error(f"Invalid path structure: {path_parts}")
        raise HTTPException(status_code=404)
    
    ics_content = body.decode("utf-8")

    # Branch on the parsed component type. A PUT to a VTODO href MUST store a
    # Task row with uid == path href (CalDAV PUT idempotency — do NOT let
    # TaskService mint a fresh uid on this path).
    if detect_component(ics_content) == "VTODO":
        parsed = parse_vtodo(ics_content)
        task_uid = parsed.get("uid") or event_uid_from_path
        if not task_uid:
            raise HTTPException(status_code=400, detail="VTODO missing UID")

        existing_task_result = await db.execute(
            select(Task).where(Task.calendar_id == calendar.id, Task.uid == task_uid)
        )
        existing_task = existing_task_result.scalar_one_or_none()

        if existing_task is not None:
            existing_task.summary = parsed.get("summary")
            existing_task.description = parsed.get("description")
            existing_task.status = parsed.get("status") or "NEEDS-ACTION"
            existing_task.priority = parsed.get("priority")
            existing_task.due = parsed.get("due")
            existing_task.completed = parsed.get("completed")
            existing_task.percent_complete = parsed.get("percent_complete")
            existing_task.raw_ics = generate_vtodo(
                uid=existing_task.uid,
                summary=existing_task.summary or "",
                status=existing_task.status,
                description=existing_task.description,
                priority=existing_task.priority,
                due=existing_task.due,
                completed=existing_task.completed,
                percent_complete=existing_task.percent_complete,
            )
            existing_task.updated_at = datetime.utcnow()
            task = existing_task
            await db.commit()
            await db.refresh(task)
        else:
            task = await TaskService(db).create_task(
                calendar_id=calendar.id,
                summary=parsed.get("summary") or "",
                description=parsed.get("description"),
                due=parsed.get("due"),
                priority=parsed.get("priority"),
                status=parsed.get("status") or "NEEDS-ACTION",
                uid=task_uid,
            )

        etag = hashlib.md5(task.raw_ics.encode()).hexdigest()
        return Response(status_code=201, headers={"ETag": f'"{etag}"'})

    uid, summary, description, dtstart, dtend, location, rrule, color, event_tz, is_all_day = parse_ics(ics_content)

    result = await db.execute(
        select(Event).where(Event.calendar_id == calendar.id, Event.uid == uid)
    )
    existing_event = result.scalar_one_or_none()
    
    if existing_event:
        existing_event.summary = summary
        existing_event.description = description
        existing_event.dtstart = dtstart
        existing_event.dtend = dtend
        existing_event.location = location
        existing_event.rrule = rrule
        existing_event.color = color
        existing_event.timezone = event_tz
        existing_event.is_all_day = is_all_day
        existing_event.raw_ics = ics_content
        existing_event.updated_at = datetime.utcnow()
        event = existing_event
    else:
        event = Event(
            calendar_id=calendar.id,
            uid=uid,
            summary=summary,
            description=description,
            dtstart=dtstart,
            dtend=dtend,
            location=location,
            color=color,
            rrule=rrule,
            timezone=event_tz,
            is_all_day=is_all_day,
            raw_ics=ics_content,
        )
        db.add(event)
    
    await db.commit()
    await db.refresh(event)
    
    etag = hashlib.md5(event.raw_ics.encode()).hexdigest()
    
    return Response(status_code=201, headers={"ETag": f'"{etag}"'})


async def handle_delete(path_parts: list, user: User, db: AsyncSession):
    logger.info(f"handle_delete called with path_parts: {path_parts}")
    
    cal_id = None
    event_uid = None
    
    # Handle different path patterns
    if len(path_parts) == 1:
        # Pattern: /dav/{event_uid}.ics - delete from default calendar
        event_uid = path_parts[0].replace(".ics", "")
        logger.info(f"Direct event DELETE for UID: {event_uid}")
        
        # Get user's default calendar or first calendar
        result = await db.execute(
            select(Calendar)
            .where(Calendar.user_id == user.id)
            .order_by(Calendar.is_default.desc(), Calendar.created_at)
        )
        calendar = result.scalars().first()
        
        if not calendar:
            raise HTTPException(status_code=404, detail="No calendar found")
    
    elif len(path_parts) >= 4 and path_parts[1] == "calendars":
        # Pattern: /dav/{username}/calendars/{calendar_id}/{event_uid}.ics
        try:
            cal_id = int(path_parts[2])
        except ValueError:
            logger.error(f"Invalid calendar ID in path: {path_parts[2]}")
            raise HTTPException(status_code=404)
        
        event_uid = path_parts[3].replace(".ics", "")
        
        calendar = await get_calendar_with_permission(cal_id, user, db, require_write=True)
        if not calendar:
            logger.error(f"No permission for calendar {cal_id} or calendar not found")
            raise HTTPException(status_code=403)
    
    else:
        logger.error(f"Invalid path structure for DELETE: {path_parts}")
        raise HTTPException(status_code=404)
    
    # Delete Event first, then Task; missing is a no-op (idempotent 204 — test_delete_is_idempotent).
    result = await db.execute(
        select(Event).where(Event.calendar_id == calendar.id, Event.uid == event_uid)
    )
    event = result.scalar_one_or_none()
    
    if event:
        await db.delete(event)
        await db.commit()
        return Response(status_code=204)
    
    task_result = await db.execute(
        select(Task).where(Task.calendar_id == calendar.id, Task.uid == event_uid)
    )
    task = task_result.scalar_one_or_none()
    if task:
        await db.delete(task)
        await db.commit()
    
    return Response(status_code=204)


_CALDAV_NS = "{urn:ietf:params:xml:ns:caldav}"


def _try_parse_report(body: bytes) -> Optional[etree._Element]:
    """Parse a REPORT body; return the root element or None on any failure.

    REPORT bodies are client-controlled; an unparseable/empty body must never
    surface as a 500. The caller gates on the root tag to decide which path
    to take.
    """
    if not body:
        return None
    try:
        return etree.fromstring(body)
    except etree.XMLSyntaxError:
        return None


def _parse_calendar_query(root: etree._Element) -> tuple[bool, bool, bool, bool]:
    """Walk a <C:calendar-query> filter and report component selection.

    Returns (vtodo_wanted, vevent_wanted, drop_completed, drop_cancelled).
    comp-filters may nest under VCALENDAR per RFC 4791 §9.7.1, so we iterate
    recursively; prop-filters are inspected only under VTODO comp-filters.
    Only the canonical RFC 4791 §7.8.9 pending-todos prop-filters are honoured
    (COMPLETED is-not-defined, STATUS text-match negate CANCELLED) — a general
    prop-filter / time-range engine is explicitly out of scope.
    """
    vtodo_wanted = False
    vevent_wanted = False
    drop_completed = False
    drop_cancelled = False
    for comp_filter in root.iter(f"{_CALDAV_NS}comp-filter"):
        name = comp_filter.get("name")
        if name == "VTODO":
            vtodo_wanted = True
            c, s = _parse_vtodo_prop_filters(comp_filter)
            drop_completed = drop_completed or c
            drop_cancelled = drop_cancelled or s
        elif name == "VEVENT":
            vevent_wanted = True
    return vtodo_wanted, vevent_wanted, drop_completed, drop_cancelled


def _parse_vtodo_prop_filters(
    vtodo_comp_filter: etree._Element,
) -> tuple[bool, bool]:
    """Canonical RFC 4791 §7.8.9 pending-todos prop-filters (direct children
    of a VTODO comp-filter). Returns (drop_completed, drop_cancelled)."""
    drop_completed = False
    drop_cancelled = False
    for prop_filter in vtodo_comp_filter.findall(f"{_CALDAV_NS}prop-filter"):
        name = prop_filter.get("name")
        if name == "COMPLETED":
            if prop_filter.find(f"{_CALDAV_NS}is-not-defined") is not None:
                drop_completed = True
        elif name == "STATUS":
            for text_match in prop_filter.findall(f"{_CALDAV_NS}text-match"):
                if (
                    text_match.get("negate-condition") == "yes"
                    and (text_match.text or "").strip().upper() == "CANCELLED"
                ):
                    drop_cancelled = True
    return drop_completed, drop_cancelled


def _emit_resource_responses(
    multistatus: etree._Element,
    href_prefix: str,
    events: list[Event],
    tasks: list[Task],
) -> None:
    # add_event_response accepts dtstart/dtend positionally for API symmetry
    # but does not serialize them, so None/None is correct for both kinds.
    for event in events:
        etag = hashlib.md5(event.raw_ics.encode()).hexdigest()
        add_event_response(
            multistatus,
            f"{href_prefix}{event.uid}.ics",
            event.uid,
            event.summary or event.uid,
            None,
            None,
            etag,
            event.raw_ics,
        )
    for task in tasks:
        etag = hashlib.md5(task.raw_ics.encode()).hexdigest()
        add_event_response(
            multistatus,
            f"{href_prefix}{task.uid}.ics",
            task.uid,
            task.summary or task.uid,
            None,
            None,
            etag,
            task.raw_ics,
        )


async def handle_report(request: Request, path_parts: list, body: bytes, user: User, db: AsyncSession):
    if len(path_parts) < 3 or path_parts[1] != "calendars":
        raise HTTPException(status_code=404)

    try:
        cal_id = int(path_parts[2])
    except ValueError:
        raise HTTPException(status_code=404)

    calendar = await get_calendar_with_permission(cal_id, user, db)
    if not calendar:
        raise HTTPException(status_code=404)

    result = await db.execute(
        select(Event).where(Event.calendar_id == calendar.id)
    )
    events = list(result.scalars().all())

    multistatus = create_multistatus()
    href_prefix = f"/dav/{user.username}/calendars/{cal_id}/"

    # M4 gate: only apply the calendar-query comp-filter logic when the body
    # parses AND its root is <C:calendar-query>. For any other REPORT root
    # (sync-collection, etc.) or an unparseable/empty body, keep the prior
    # all-events path verbatim so existing sync-collection consumers see no
    # change. An invalid body must never raise 500.
    root = _try_parse_report(body)
    if root is not None and root.tag == f"{_CALDAV_NS}calendar-query":
        vtodo_wanted, vevent_wanted, drop_completed, drop_cancelled = (
            _parse_calendar_query(root)
        )
        # Neither/unknown component filter → treat as both (RFC 4791 §7.8).
        if not vtodo_wanted and not vevent_wanted:
            vtodo_wanted = True
            vevent_wanted = True

        tasks: list[Task] = []
        if vtodo_wanted:
            task_result = await db.execute(
                select(Task).where(Task.calendar_id == calendar.id)
            )
            tasks = list(task_result.scalars().all())
            if drop_completed:
                tasks = [t for t in tasks if t.completed is None]
            if drop_cancelled:
                tasks = [
                    t for t in tasks if (t.status or "").upper() != "CANCELLED"
                ]

        events_to_emit = events if vevent_wanted else []
        _emit_resource_responses(
            multistatus, href_prefix, events_to_emit, tasks
        )
        # Consistent with the B2 fix T4 applied in PROPFIND: hash the full
        # events+tasks set actually considered for this calendar.
        sync_token = compute_sync_token(cal_id, list(events_to_emit) + tasks)
    else:
        _emit_resource_responses(
            multistatus, href_prefix, events, []
        )
        sync_token = compute_sync_token(cal_id, events)

    # RFC 6578 §3.4: a sync-collection REPORT response MUST include a
    # <sync-token> as a direct child of <multistatus>. Always include it
    # (even for calendar-query / empty bodies) so strict clients that call
    # .Single() on the token element never crash with InvalidOperationException.
    add_sync_token(multistatus, sync_token)

    return FastAPIResponse(
        content=xml_to_string(multistatus),
        media_type="application/xml; charset=utf-8",
        status_code=207,
    )
