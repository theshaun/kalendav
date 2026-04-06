from fastapi import APIRouter, Request, Response, Depends, HTTPException, status
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from lxml import etree
from app.database import get_db
from app.models import User, Calendar, Event, CalendarShare
from app.auth import get_current_user
from app.caldav.xml_responses import (
    create_multistatus,
    add_response,
    add_propstat,
    add_principal_response,
    add_calendar_response,
    add_event_response,
    xml_to_string,
)
from app.caldav.ics_parser import parse_ics, generate_ics
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
            .options(selectinload(Calendar.shares))
            .where(Calendar.user_id == user.id)
        )
        owned_calendars = result.scalars().all()
        
        result = await db.execute(
            select(CalendarShare)
            .options(selectinload(CalendarShare.calendar))
            .where(CalendarShare.user_id == user.id)
        )
        shared = result.scalars().all()
        shared_calendars = [s.calendar for s in shared]
        
        all_calendars = list(owned_calendars) + shared_calendars
        
        if depth == "1":
            add_response(multistatus, f"/dav/principals/{user.username}/calendars/")
        
        for cal in all_calendars:
            href = f"/dav/{user.username}/calendars/{cal.id}/"
            add_calendar_response(
                multistatus,
                href,
                cal.id,
                cal.name,
                cal.description,
                cal.color or "#3B82F6",
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
        
        add_calendar_response(
            multistatus,
            f"/dav/{user.username}/calendars/{cal_id}/",
            calendar.id,
            calendar.name,
            calendar.description,
            calendar.color or "#3B82F6",
        )
        
        if depth == "1":
            result = await db.execute(
                select(Event).where(Event.calendar_id == calendar.id)
            )
            events = result.scalars().all()
            
            for event in events:
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
    
    elif len(path_parts) >= 2 and path_parts[1] == "calendars":
        result = await db.execute(
            select(Calendar)
            .options(selectinload(Calendar.shares))
            .where(Calendar.user_id == user.id)
        )
        owned_calendars = result.scalars().all()
        
        result = await db.execute(
            select(CalendarShare)
            .options(selectinload(CalendarShare.calendar))
            .where(CalendarShare.user_id == user.id)
        )
        shared = result.scalars().all()
        shared_calendars = [s.calendar for s in shared]
        
        all_calendars = list(owned_calendars) + shared_calendars
        
        if depth == "1":
            add_response(multistatus, f"/dav/{user.username}/calendars/")
        
        for cal in all_calendars:
            href = f"/dav/{user.username}/calendars/{cal.id}/"
            add_calendar_response(
                multistatus,
                href,
                cal.id,
                cal.name,
                cal.description,
                cal.color or "#3B82F6",
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
        # Pattern: /dav/{event_uid}.ics - get from default calendar
        event_uid = path_parts[0].replace(".ics", "")
        
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
        
        # Get specific event
        result = await db.execute(
            select(Event).where(Event.calendar_id == calendar.id, Event.uid == event_uid)
        )
        event = result.scalar_one_or_none()
        
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        
        events = [event]
    
    elif len(path_parts) >= 5 and path_parts[1] == "calendars":
        # Pattern: /dav/{username}/calendars/{calendar_id}/{event_uid}.ics
        try:
            cal_id = int(path_parts[2])
        except ValueError:
            raise HTTPException(status_code=404)
        
        calendar = await get_calendar_with_permission(cal_id, user, db)
        if not calendar:
            raise HTTPException(status_code=404)
        
        # Get all events from calendar
        result = await db.execute(
            select(Event).where(Event.calendar_id == calendar.id)
        )
        events = result.scalars().all()
    
    else:
        logger.error(f"Invalid path structure for GET: {path_parts}")
        raise HTTPException(status_code=404)
    
    from app.caldav.ics_parser import generate_calendar_ics
    ics_content = generate_calendar_ics(events, calendar.name)
    
    return FastAPIResponse(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
    )


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
    uid, summary, description, dtstart, dtend, location, rrule = parse_ics(ics_content)
    
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
            rrule=rrule,
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
    
    # Find and delete the event
    result = await db.execute(
        select(Event).where(Event.calendar_id == calendar.id, Event.uid == event_uid)
    )
    event = result.scalar_one_or_none()
    
    if event:
        await db.delete(event)
        await db.commit()
    
    return Response(status_code=204)


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
    
    multistatus = create_multistatus()
    
    result = await db.execute(
        select(Event).where(Event.calendar_id == calendar.id)
    )
    events = result.scalars().all()
    
    for event in events:
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
    
    return FastAPIResponse(
        content=xml_to_string(multistatus),
        media_type="application/xml; charset=utf-8",
        status_code=207,
    )
