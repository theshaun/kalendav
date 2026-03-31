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

router = APIRouter()


def check_calendar_permission(user: User, calendar: Calendar, require_write: bool = False) -> bool:
    if calendar.user_id == user.id:
        return True
    
    for share in calendar.shares:
        if share.user_id == user.id:
            if require_write:
                return share.permission.value == "read_write"
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
    
    elif len(path_parts) >= 2 and path_parts[0] == "principals":
        add_principal_response(
            multistatus,
            f"/dav/principals/{user.username}/",
            f"/dav/principals/{user.username}/",
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
    
    elif len(path_parts) >= 4 and path_parts[1] == "calendars":
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
    
    return FastAPIResponse(
        content=xml_to_string(multistatus),
        media_type="application/xml; charset=utf-8",
        status_code=207,
        headers={"DAV": "1, 2, 3, calendar-access, calendar-schedule"},
    )


async def handle_proppatch(request: Request, path_parts: list, user: User, db: AsyncSession):
    if len(path_parts) < 4 or path_parts[1] != "calendars":
        raise HTTPException(status_code=404)
    
    try:
        cal_id = int(path_parts[2])
    except ValueError:
        raise HTTPException(status_code=404)
    
    calendar = await get_calendar_with_permission(cal_id, user, db, require_write=True)
    if not calendar:
        raise HTTPException(status_code=403)
    
    multistatus = create_multistatus()
    response = add_response(multistatus, f"/dav/{user.username}/calendars/{cal_id}/")
    add_propstat(response, "HTTP/1.1 200 OK")
    
    return FastAPIResponse(
        content=xml_to_string(multistatus),
        media_type="application/xml; charset=utf-8",
        status_code=207,
    )


async def handle_mkcalendar(request: Request, path_parts: list, user: User, db: AsyncSession):
    if len(path_parts) < 4 or path_parts[1] != "calendars":
        raise HTTPException(status_code=400)
    
    calendar_name = path_parts[3] if len(path_parts) > 3 else "New Calendar"
    
    new_calendar = Calendar(
        user_id=user.id,
        name=calendar_name,
    )
    db.add(new_calendar)
    await db.commit()
    await db.refresh(new_calendar)
    
    return Response(status_code=201)


async def handle_get(path_parts: list, user: User, db: AsyncSession):
    if len(path_parts) < 5 or path_parts[1] != "calendars":
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
    events = result.scalars().all()
    
    from app.caldav.ics_parser import generate_calendar_ics
    ics_content = generate_calendar_ics(events, calendar.name)
    
    return FastAPIResponse(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
    )


async def handle_put(path_parts: list, body: bytes, user: User, db: AsyncSession):
    if len(path_parts) < 5 or path_parts[1] != "calendars":
        raise HTTPException(status_code=404)
    
    try:
        cal_id = int(path_parts[2])
    except ValueError:
        raise HTTPException(status_code=404)
    
    calendar = await get_calendar_with_permission(cal_id, user, db, require_write=True)
    if not calendar:
        raise HTTPException(status_code=403)
    
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
    if len(path_parts) < 5 or path_parts[1] != "calendars":
        raise HTTPException(status_code=404)
    
    try:
        cal_id = int(path_parts[2])
    except ValueError:
        raise HTTPException(status_code=404)
    
    event_uid = path_parts[4].replace(".ics", "")
    
    calendar = await get_calendar_with_permission(cal_id, user, db, require_write=True)
    if not calendar:
        raise HTTPException(status_code=403)
    
    result = await db.execute(
        select(Event).where(Event.calendar_id == calendar.id, Event.uid == event_uid)
    )
    event = result.scalar_one_or_none()
    
    if event:
        await db.delete(event)
        await db.commit()
    
    return Response(status_code=204)


async def handle_report(request: Request, path_parts: list, body: bytes, user: User, db: AsyncSession):
    if len(path_parts) < 4 or path_parts[1] != "calendars":
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
