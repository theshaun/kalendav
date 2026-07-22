from fastapi import APIRouter, Body, Depends, HTTPException, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response as FastAPIResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import User, Calendar, Event, CalendarShare, APIKey
from app.models.share import SharePermission
from app.schemas import (
    UserCreate, UserUpdate, UserResponse,
    CalendarCreate, CalendarUpdate, CalendarResponse,
    CalendarShareCreate, CalendarShareResponse,
    APIKeyCreate, APIKeyResponse,
)
from app.auth.basic import hash_password, verify_password
from app.auth.basic import generate_api_key, hash_api_key
from app.auth.session_deps import get_current_user_session, get_current_user_session_optional
from app.auth.session import set_session_cookie, clear_session_cookie
from app.services.event_service import EventService
from app.caldav.ics_parser import build_rrule, parse_ics_bulk, generate_calendar_ics
from app.config import settings, get_base_uri
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta, timezone
import json
from typing import Optional
from zoneinfo import ZoneInfo

from app.admin.template_filters import register_template_filters

router = APIRouter()
templates = Jinja2Templates(directory="app/admin/templates")
register_template_filters(templates.env)


def _resolve_client_tz(tz_name: Optional[str]) -> ZoneInfo:
    # Browser sends IANA name via Intl.DateTimeFormat; fall back to instance default.
    if not tz_name:
        return settings.tz
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return settings.tz


class _LocalEventView:
    """Wraps an Event, exposing dtstart/dtend shifted into the viewer's tz.

    The template reads ``event.dtstart.strftime('%Y-%m-%dT%H:%M')`` to populate
    a ``datetime-local`` input. The stored DB value is naive UTC; without this
    shift the form would show UTC wall-clock instead of the viewer's local time.
    Other attributes are passed through unchanged.
    """
    def __init__(self, event, client_tz: ZoneInfo):
        self._event = event
        self._client_tz = client_tz

    def __getattr__(self, name):
        return getattr(self._event, name)

    @property
    def dtstart(self):
        return self._event.dtstart.replace(tzinfo=timezone.utc).astimezone(self._client_tz)

    @property
    def dtend(self):
        if self._event.dtend is None:
            return None
        return self._event.dtend.replace(tzinfo=timezone.utc).astimezone(self._client_tz)


def _event_local_for_form(event, client_tz: ZoneInfo):
    if event is None or event.is_all_day:
        return event
    return _LocalEventView(event, client_tz)


def _event_zone(event) -> ZoneInfo:
    # Render in the event's own tz so web matches phone ICS output, not the viewer's tz.
    tz_name = getattr(event, "timezone", None)
    if not tz_name:
        return settings.tz
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return settings.tz


def check_admin(user: User):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_session_optional(request, db)
    if user:
        return RedirectResponse(url="/admin/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # Case-insensitive username lookup
    result = await db.execute(
        select(User).where(func.lower(User.username) == username.lower())
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password"},
        )
    
    response = RedirectResponse(url="/admin/", status_code=302)
    return set_session_cookie(response, user.id)


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/admin/login", status_code=302)
    return clear_session_cookie(response)


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    # Redirect non-admin users to their own dashboard
    if not user.is_admin:
        return RedirectResponse(url="/admin/my-dashboard", status_code=302)
    
    result = await db.execute(select(User))
    users = result.scalars().all()
    
    result = await db.execute(select(Calendar))
    calendars = result.scalars().all()
    
    result = await db.execute(select(Event))
    events = result.scalars().all()
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "users_count": len(users),
            "calendars_count": len(calendars),
            "events_count": len(events),
            "base_uri": get_base_uri(request),
        },
    )


@router.get("/users", response_class=HTMLResponse)
async def list_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    result = await db.execute(
        select(User).options(selectinload(User.calendars))
    )
    users = result.scalars().all()
    
    return templates.TemplateResponse(
        "users.html",
        {"request": request, "user": user, "users": users},
    )


@router.get("/users/create", response_class=HTMLResponse)
async def create_user_form(
    request: Request,
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    return templates.TemplateResponse(
        "user_form.html",
        {"request": request, "user": user, "edit_user": None},
    )


@router.post("/users/create")
async def create_user(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    is_admin: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    new_user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        is_admin=is_admin,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    default_calendar = Calendar(
        name=f"{username}'s Calendar",
        description=f"Default calendar for {username}",
        color=Calendar.DEFAULT_COLOR,
        user_id=new_user.id,
    )
    db.add(default_calendar)
    await db.commit()
    
    return RedirectResponse(url="/admin/users", status_code=303)


@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
async def edit_user_form(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    result = await db.execute(select(User).where(User.id == user_id))
    edit_user = result.scalar_one_or_none()
    
    if not edit_user:
        raise HTTPException(status_code=404)
    
    return templates.TemplateResponse(
        "user_form.html",
        {"request": request, "user": user, "edit_user": edit_user},
    )


@router.post("/users/{user_id}/edit")
async def edit_user(
    user_id: int,
    email: str = Form(...),
    password: Optional[str] = Form(None),
    is_admin: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    result = await db.execute(select(User).where(User.id == user_id))
    edit_user = result.scalar_one_or_none()
    
    if not edit_user:
        raise HTTPException(status_code=404)
    
    edit_user.email = email
    edit_user.is_admin = is_admin
    
    if password:
        edit_user.password_hash = hash_password(password)
    
    await db.commit()
    
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/delete")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    result = await db.execute(select(User).where(User.id == user_id))
    delete_user = result.scalar_one_or_none()
    
    if not delete_user:
        raise HTTPException(status_code=404)
    
    await db.delete(delete_user)
    await db.commit()
    
    return RedirectResponse(url="/admin/users", status_code=303)


@router.get("/calendars", response_class=HTMLResponse)
async def list_calendars(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    result = await db.execute(
        select(Calendar).options(selectinload(Calendar.user), selectinload(Calendar.shares))
    )
    calendars = result.scalars().all()
    
    return templates.TemplateResponse(
        "calendars.html",
        {"request": request, "user": user, "calendars": calendars},
    )


@router.get("/calendars/create", response_class=HTMLResponse)
async def create_calendar_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    result = await db.execute(select(User))
    users = result.scalars().all()
    
    return templates.TemplateResponse(
        "calendar_form.html",
        {"request": request, "user": user, "calendar": None, "users": users},
    )


@router.post("/calendars/create")
async def create_calendar(
    name: str = Form(...),
    description: str = Form(None),
    color: str = Form(Calendar.DEFAULT_COLOR),
    user_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    new_calendar = Calendar(
        name=name,
        description=description,
        color=color,
        user_id=user_id,
    )
    db.add(new_calendar)
    await db.commit()
    
    return RedirectResponse(url="/admin/calendars", status_code=303)


@router.get("/calendars/{calendar_id}/edit", response_class=HTMLResponse)
async def edit_calendar_form(
    calendar_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    result = await db.execute(
        select(Calendar).options(selectinload(Calendar.user)).where(Calendar.id == calendar_id)
    )
    calendar = result.scalar_one_or_none()
    
    if not calendar:
        raise HTTPException(status_code=404)
    
    result = await db.execute(select(User))
    users = result.scalars().all()
    
    return templates.TemplateResponse(
        "calendar_form.html",
        {"request": request, "user": user, "calendar": calendar, "users": users},
    )


@router.post("/calendars/{calendar_id}/edit")
async def edit_calendar(
    calendar_id: int,
    name: str = Form(...),
    description: str = Form(None),
    color: str = Form(Calendar.DEFAULT_COLOR),
    user_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    result = await db.execute(select(Calendar).where(Calendar.id == calendar_id))
    calendar = result.scalar_one_or_none()
    
    if not calendar:
        raise HTTPException(status_code=404)
    
    calendar.name = name
    calendar.description = description
    calendar.color = color
    calendar.user_id = user_id
    
    await db.commit()
    
    return RedirectResponse(url="/admin/calendars", status_code=303)


@router.post("/calendars/{calendar_id}/delete")
async def delete_calendar(
    calendar_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    result = await db.execute(select(Calendar).where(Calendar.id == calendar_id))
    calendar = result.scalar_one_or_none()
    
    if not calendar:
        raise HTTPException(status_code=404)
    
    await db.delete(calendar)
    await db.commit()
    
    return RedirectResponse(url="/admin/calendars", status_code=303)


@router.get("/calendars/{calendar_id}/shares", response_class=HTMLResponse)
async def manage_shares(
    calendar_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    result = await db.execute(
        select(Calendar)
        .options(selectinload(Calendar.shares).selectinload(CalendarShare.user))
        .where(Calendar.id == calendar_id)
    )
    calendar = result.scalar_one_or_none()
    
    if not calendar:
        raise HTTPException(status_code=404)
    
    result = await db.execute(select(User))
    users = result.scalars().all()
    
    return templates.TemplateResponse(
        "shares.html",
        {"request": request, "user": user, "calendar": calendar, "users": users},
    )


@router.post("/calendars/{calendar_id}/shares")
async def add_share(
    calendar_id: int,
    user_id: int = Form(...),
    permission: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    result = await db.execute(
        select(CalendarShare)
        .where(CalendarShare.calendar_id == calendar_id, CalendarShare.user_id == user_id)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        existing.permission = SharePermission(permission)
    else:
        share = CalendarShare(
            calendar_id=calendar_id,
            user_id=user_id,
            permission=SharePermission(permission),
        )
        db.add(share)
    
    await db.commit()
    
    return RedirectResponse(url=f"/admin/calendars/{calendar_id}/shares", status_code=303)


@router.post("/shares/{share_id}/delete")
async def delete_share(
    share_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    result = await db.execute(select(CalendarShare).where(CalendarShare.id == share_id))
    share = result.scalar_one_or_none()
    
    if share:
        calendar_id = share.calendar_id
        await db.delete(share)
        await db.commit()
        return RedirectResponse(url=f"/admin/calendars/{calendar_id}/shares", status_code=303)
    
    raise HTTPException(status_code=404)


@router.get("/api-keys", response_class=HTMLResponse)
async def list_api_keys(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    result = await db.execute(
        select(APIKey).options(selectinload(APIKey.user))
    )
    api_keys = result.scalars().all()
    
    return templates.TemplateResponse(
        "api_keys.html",
        {"request": request, "user": user, "api_keys": api_keys},
    )


@router.get("/api-keys/create", response_class=HTMLResponse)
async def create_api_key_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    result = await db.execute(select(User))
    users = result.scalars().all()
    
    return templates.TemplateResponse(
        "api_key_form.html",
        {"request": request, "user": user, "api_key": None, "users": users, "generated_key": None},
    )


@router.post("/api-keys/create", response_class=HTMLResponse)
async def create_api_key(
    request: Request,
    name: str = Form(...),
    user_id: int = Form(...),
    expires_at: str = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    
    expires = None
    if expires_at:
        try:
            expires = datetime.fromisoformat(expires_at)
        except:
            pass
    
    api_key = APIKey(
        name=name,
        user_id=user_id,
        key_hash=key_hash,
        expires_at=expires,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    
    result = await db.execute(select(User))
    users = result.scalars().all()
    
    return templates.TemplateResponse(
        "api_key_form.html",
        {
            "request": request,
            "user": user,
            "api_key": api_key,
            "users": users,
            "generated_key": raw_key,
        },
    )


@router.post("/api-keys/{key_id}/delete")
async def delete_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    check_admin(user)
    
    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()
    
    if api_key:
        await db.delete(api_key)
        await db.commit()
    
    return RedirectResponse(url="/admin/api-keys", status_code=303)


# ============== User Dashboard (for non-admin users) ==============

@router.get("/my-dashboard", response_class=HTMLResponse)
async def user_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    # Both admin and non-admin can access their own dashboard
    result = await db.execute(
        select(Calendar).where(Calendar.user_id == user.id)
    )
    calendars = result.scalars().all()
    
    result = await db.execute(
        select(APIKey).where(APIKey.user_id == user.id)
    )
    api_keys = result.scalars().all()
    
    # Get events count from user's calendars
    calendar_ids = [c.id for c in calendars]
    events_count = 0
    if calendar_ids:
        result = await db.execute(
            select(Event).where(Event.calendar_id.in_(calendar_ids))
        )
        events = result.scalars().all()
        events_count = len(events)
    
    return templates.TemplateResponse(
        "user_dashboard.html",
        {
            "request": request,
            "user": user,
            "calendars_count": len(calendars),
            "api_keys_count": len(api_keys),
            "events_count": events_count,
            "base_uri": get_base_uri(request),
        },
    )


@router.get("/my-api-keys", response_class=HTMLResponse)
async def user_list_api_keys(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    result = await db.execute(
        select(APIKey).where(APIKey.user_id == user.id)
    )
    api_keys = result.scalars().all()
    
    return templates.TemplateResponse(
        "user_api_keys.html",
        {"request": request, "user": user, "api_keys": api_keys},
    )


@router.get("/my-api-keys/create", response_class=HTMLResponse)
async def user_create_api_key_form(
    request: Request,
    user: User = Depends(get_current_user_session),
):
    return templates.TemplateResponse(
        "user_api_key_form.html",
        {"request": request, "user": user, "api_key": None, "generated_key": None},
    )


@router.post("/my-api-keys/create", response_class=HTMLResponse)
async def user_create_api_key(
    request: Request,
    name: str = Form(...),
    expires_at: str = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    
    expires = None
    if expires_at:
        try:
            expires = datetime.fromisoformat(expires_at)
        except:
            pass
    
    api_key = APIKey(
        name=name,
        user_id=user.id,
        key_hash=key_hash,
        expires_at=expires,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    
    return templates.TemplateResponse(
        "user_api_key_form.html",
        {
            "request": request,
            "user": user,
            "api_key": api_key,
            "generated_key": raw_key,
        },
    )


@router.post("/my-api-keys/{key_id}/delete")
async def user_delete_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    result = await db.execute(
        select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user.id)
    )
    api_key = result.scalar_one_or_none()
    
    if api_key:
        await db.delete(api_key)
        await db.commit()
    
    return RedirectResponse(url="/admin/my-api-keys", status_code=303)


@router.get("/my-calendars", response_class=HTMLResponse)
async def user_list_calendars(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    result = await db.execute(
        select(Calendar)
        .options(selectinload(Calendar.shares))
        .where(Calendar.user_id == user.id)
    )
    owned_calendars = result.scalars().all()
    
    result = await db.execute(
        select(CalendarShare)
        .options(
            selectinload(CalendarShare.calendar).selectinload(Calendar.user),
            selectinload(CalendarShare.calendar).selectinload(Calendar.shares)
        )
        .where(CalendarShare.user_id == user.id)
    )
    shares = result.scalars().all()
    shared_calendars = []
    for share in shares:
        if share.calendar:
            shared_calendars.append({
                'calendar': share.calendar,
                'permission': share.permission.value,
                'owner': share.calendar.user
            })
    
    return templates.TemplateResponse(
        "user_calendars.html",
        {
            "request": request,
            "user": user,
            "calendars": owned_calendars,
            "shared_calendars": shared_calendars,
        },
    )


@router.get("/my-calendars/create", response_class=HTMLResponse)
async def user_create_calendar_form(
    request: Request,
    user: User = Depends(get_current_user_session),
):
    return templates.TemplateResponse(
        "user_calendar_form.html",
        {"request": request, "user": user, "calendar": None},
    )


@router.get("/my-calendars/{calendar_id}/edit", response_class=HTMLResponse)
async def user_edit_calendar_form(
    calendar_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    result = await db.execute(
        select(Calendar).where(Calendar.id == calendar_id, Calendar.user_id == user.id)
    )
    calendar = result.scalar_one_or_none()
    
    if not calendar:
        raise HTTPException(status_code=404)
    
    return templates.TemplateResponse(
        "user_calendar_form.html",
        {"request": request, "user": user, "calendar": calendar},
    )


@router.post("/my-calendars/{calendar_id}/edit")
async def user_edit_calendar(
    calendar_id: int,
    name: str = Form(...),
    description: str = Form(None),
    color: str = Form(Calendar.DEFAULT_COLOR),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    result = await db.execute(
        select(Calendar).where(Calendar.id == calendar_id, Calendar.user_id == user.id)
    )
    calendar = result.scalar_one_or_none()
    
    if not calendar:
        raise HTTPException(status_code=404)
    
    calendar.name = name
    calendar.description = description
    calendar.color = color
    
    await db.commit()
    
    return RedirectResponse(url="/admin/my-calendars", status_code=303)


@router.post("/my-calendars/{calendar_id}/delete")
async def user_delete_calendar(
    calendar_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    result = await db.execute(
        select(Calendar).where(Calendar.id == calendar_id, Calendar.user_id == user.id)
    )
    calendar = result.scalar_one_or_none()
    
    if calendar:
        await db.delete(calendar)
        await db.commit()
    
    return RedirectResponse(url="/admin/my-calendars", status_code=303)


@router.post("/my-calendars/create")
async def user_create_calendar(
    name: str = Form(...),
    description: str = Form(None),
    color: str = Form(Calendar.DEFAULT_COLOR),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    new_calendar = Calendar(
        name=name,
        description=description,
        color=color,
        user_id=user.id,
    )
    db.add(new_calendar)
    await db.commit()
    
    return RedirectResponse(url="/admin/my-calendars", status_code=303)


@router.get("/my-calendars/{calendar_id}/shares", response_class=HTMLResponse)
async def user_manage_shares(
    calendar_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    # Only allow user to manage shares for their own calendars
    result = await db.execute(
        select(Calendar)
        .options(selectinload(Calendar.shares).selectinload(CalendarShare.user))
        .where(Calendar.id == calendar_id, Calendar.user_id == user.id)
    )
    calendar = result.scalar_one_or_none()
    
    if not calendar:
        raise HTTPException(status_code=404)
    
    result = await db.execute(select(User))
    users = result.scalars().all()
    
    return templates.TemplateResponse(
        "user_shares.html",
        {"request": request, "user": user, "calendar": calendar, "users": users},
    )


@router.post("/my-calendars/{calendar_id}/shares")
async def user_add_share(
    calendar_id: int,
    user_id: int = Form(...),
    permission: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    # Verify calendar belongs to current user
    result = await db.execute(
        select(Calendar).where(Calendar.id == calendar_id, Calendar.user_id == user.id)
    )
    calendar = result.scalar_one_or_none()
    
    if not calendar:
        raise HTTPException(status_code=404)
    
    result = await db.execute(
        select(CalendarShare)
        .where(CalendarShare.calendar_id == calendar_id, CalendarShare.user_id == user_id)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        existing.permission = SharePermission(permission)
    else:
        share = CalendarShare(
            calendar_id=calendar_id,
            user_id=user_id,
            permission=SharePermission(permission),
        )
        db.add(share)
    
    await db.commit()
    
    return RedirectResponse(url=f"/admin/my-calendars/{calendar_id}/shares", status_code=303)


@router.post("/my-shares/{share_id}/delete")
async def user_delete_share(
    share_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    result = await db.execute(
        select(CalendarShare)
        .options(selectinload(CalendarShare.calendar))
        .where(CalendarShare.id == share_id)
    )
    share = result.scalar_one_or_none()
    
    if share and share.calendar.user_id == user.id:
        calendar_id = share.calendar_id
        await db.delete(share)
        await db.commit()
        return RedirectResponse(url=f"/admin/my-calendars/{calendar_id}/shares", status_code=303)
    
    raise HTTPException(status_code=404)


# ============== Web Calendar ==============

@router.get("/calendar", response_class=HTMLResponse)
async def web_calendar(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    result = await db.execute(
        select(Calendar).where(Calendar.user_id == user.id)
    )
    owned_calendars = result.scalars().all()
    
    result = await db.execute(
        select(CalendarShare)
        .options(selectinload(CalendarShare.calendar))
        .where(
            CalendarShare.user_id == user.id,
            CalendarShare.permission.in_([SharePermission.READ, SharePermission.WRITE, SharePermission.ADMIN])
        )
    )
    shares = result.scalars().all()
    
    writable_ids = set(c.id for c in owned_calendars)
    for share in shares:
        if share.permission in [SharePermission.WRITE, SharePermission.ADMIN]:
            writable_ids.add(share.calendar_id)
    
    all_calendars = list(owned_calendars) + [s.calendar for s in shares if s.calendar_id not in [c.id for c in owned_calendars]]
    
    return templates.TemplateResponse(
        "calendar.html",
        {
            "request": request,
            "user": user,
            "calendars": all_calendars,
            "writable_calendar_ids": list(writable_ids),
        },
    )


@router.get("/calendar/events", response_class=JSONResponse)
async def get_calendar_events(
    start: str,
    end: str,
    tz: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    event_service = EventService(db)
    
    client_tz = ZoneInfo(tz) if tz else timezone.utc
    
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=client_tz)
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=client_tz)
    except ValueError:
        start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=client_tz)
        end_dt = (datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)).replace(tzinfo=client_tz)
    
    start_utc = start_dt.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_dt.astimezone(timezone.utc).replace(tzinfo=None)
    
    events = await event_service.get_events_for_user(user.id, start_utc, end_utc)
    
    events_data = []
    for event in events:
        if event.is_all_day:
            dtstart_local = event.dtstart.replace(tzinfo=None)
            dtend_local = event.dtend.replace(tzinfo=None) if event.dtend else dtstart_local + timedelta(days=1)
            event_start = dtstart_local.date().isoformat()
            event_end = dtend_local.date().isoformat()
        else:
            event_tz = _event_zone(event)
            dtstart_utc = event.dtstart.replace(tzinfo=timezone.utc)
            dtstart_local = dtstart_utc.astimezone(event_tz)
            if event.dtend:
                dtend_utc = event.dtend.replace(tzinfo=timezone.utc)
                dtend_local = dtend_utc.astimezone(event_tz)
            else:
                dtend_local = dtstart_local + timedelta(hours=1)
            event_start = dtstart_local.isoformat()
            event_end = dtend_local.isoformat()
        
        event_data = {
            "id": event.id,
            "title": event.summary or "(No title)",
            "start": event_start,
            "end": event_end,
            "allDay": event.is_all_day,
            "calendarId": event.calendar_id,
            "calendarName": event.calendar.name if event.calendar else "",
            "calendarColor": event.calendar.color if event.calendar else Calendar.DEFAULT_COLOR,
            "color": event.color,
            "location": event.location,
            "description": event.description,
        }
        if event.rrule and event.rrule.strip():
            # Convert rrule string to FullCalendar format
            try:
                rrule_str = event.rrule.strip()
                
                # Remove RRULE: prefix if present
                if rrule_str.upper().startswith('RRULE:'):
                    rrule_str = rrule_str[6:]
                
                # Handle malformed vRecur format from old bug
                if rrule_str.startswith('vRecur('):
                    # Extract the dict part from vRecur({...})
                    import ast
                    dict_str = rrule_str[7:-1]  # Remove 'vRecur(' and ')'
                    rrule_dict = ast.literal_eval(dict_str)
                    
                    # Convert vRecur dict to proper format
                    rrule_obj = {}
                    for key, value in rrule_dict.items():
                        key_lower = key.lower()
                        if isinstance(value, list) and len(value) > 0:
                            value = value[0]
                        
                        if key_lower in ['interval', 'count']:
                            rrule_obj[key_lower] = int(value)
                        elif key_lower == 'freq':
                            rrule_obj['freq'] = str(value).lower()
                        elif key_lower == 'until':
                            until_val = str(value)
                            # Convert to ISO format for JavaScript
                            if len(until_val) == 8:
                                rrule_obj[key_lower] = f"{until_val[:4]}-{until_val[4:6]}-{until_val[6:8]}"
                            elif 'T' in until_val:
                                rrule_obj[key_lower] = until_val.replace('Z', '')
                            else:
                                rrule_obj[key_lower] = until_val
                        elif key_lower == 'byday':
                            if isinstance(value, list):
                                rrule_obj['byday'] = value
                            else:
                                rrule_obj['byday'] = str(value).split(',')
                        else:
                            rrule_obj[key_lower] = str(value)
                else:
                    # Handle proper RRULE format: FREQ=WEEKLY;INTERVAL=2;COUNT=10
                    rrule_obj = {}
                    parts = rrule_str.split(';')
                    for part in parts:
                        part = part.strip()
                        if '=' in part:
                            key, value = part.split('=', 1)
                            key_lower = key.strip().lower()
                            value = value.strip()
                            
                            if key_lower in ['interval', 'count']:
                                rrule_obj[key_lower] = int(value)
                            elif key_lower == 'freq':
                                rrule_obj['freq'] = value.lower()
                            elif key_lower == 'until':
                                # Convert to ISO format for JavaScript
                                if len(value) == 8:
                                    rrule_obj[key_lower] = f"{value[:4]}-{value[4:6]}-{value[6:8]}"
                                elif 'T' in value:
                                    rrule_obj[key_lower] = value.replace('Z', '')
                                else:
                                    rrule_obj[key_lower] = value
                            elif key_lower == 'byday':
                                rrule_obj['byday'] = value.split(',')
                            else:
                                rrule_obj[key_lower] = value
                
                # Only add rrule if we have a valid frequency
                if 'freq' in rrule_obj and rrule_obj['freq']:
                    # Add dtstart for FullCalendar rrule plugin
                    rrule_obj['dtstart'] = dtstart_local.isoformat()
                    event_data["rrule"] = rrule_obj
            except Exception as e:
                # Log error but don't break the calendar
                import logging
                logging.error(f"Error parsing rrule '{event.rrule}': {e}")
                pass
        events_data.append(event_data)
    
    return JSONResponse(content=events_data)


@router.get("/calendar/events/new", response_class=HTMLResponse)
async def new_event_modal(
    request: Request,
    date: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    event_service = EventService(db)
    writable_ids = await event_service.get_writable_calendars(user.id)
    
    result = await db.execute(
        select(Calendar).where(Calendar.id.in_(writable_ids))
    )
    calendars = result.scalars().all()
    
    default_date = date or datetime.now().strftime("%Y-%m-%d")
    default_start = start
    default_end = end
    
    return templates.TemplateResponse(
        "partials/event_modal.html",
        {
            "request": request,
            "user": user,
            "event": None,
            "calendars": calendars,
            "default_date": default_date,
            "default_start": default_start,
            "default_end": default_end,
            "is_new": True,
        },
    )


@router.get("/calendar/events/{event_id}", response_class=HTMLResponse)
async def edit_event_modal(
    event_id: int,
    request: Request,
    tz: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    event_service = EventService(db)

    if not await event_service.can_edit_event(event_id, user.id):
        raise HTTPException(status_code=403, detail="Cannot edit this event")

    event = await event_service.get_by_id(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    writable_ids = await event_service.get_writable_calendars(user.id)
    result = await db.execute(
        select(Calendar).where(Calendar.id.in_(writable_ids))
    )
    calendars = result.scalars().all()

    client_tz = _resolve_client_tz(tz)
    event_local = _event_local_for_form(event, client_tz)

    return templates.TemplateResponse(
        "partials/event_modal.html",
        {
            "request": request,
            "user": user,
            "event": event_local,
            "calendars": calendars,
            "default_date": None,
            "is_new": False,
        },
    )


@router.post("/calendar/events")
async def create_event(
    calendar_id: int = Form(...),
    summary: str = Form(...),
    dtstart: str = Form(...),
    dtend: Optional[str] = Form(None),
    is_all_day: bool = Form(False),
    location: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    color: Optional[str] = Form(None),
    rrule_freq: Optional[str] = Form(None),
    rrule_interval: int = Form(1),
    rrule_count: Optional[int] = Form(None),
    rrule_until: Optional[str] = Form(None),
    tz: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    event_service = EventService(db)
    writable_ids = await event_service.get_writable_calendars(user.id)
    
    if calendar_id not in writable_ids:
        raise HTTPException(status_code=403, detail="Cannot create event in this calendar")
    
    # Empty/whitespace tz must collapse to None so `if tz` falls back to UTC.
    tz = (tz or "").strip() or None
    client_tz = ZoneInfo(tz) if tz else timezone.utc
    
    try:
        if "T" in dtstart:
            dtstart_dt = datetime.fromisoformat(dtstart.replace("Z", "+00:00"))
            if dtstart_dt.tzinfo is None:
                dtstart_dt = dtstart_dt.replace(tzinfo=client_tz)
        else:
            dtstart_dt = datetime.strptime(dtstart, "%Y-%m-%d").replace(tzinfo=client_tz)
    except ValueError:
        dtstart_dt = datetime.now(client_tz)
    
    dtstart_utc = dtstart_dt.astimezone(timezone.utc).replace(tzinfo=None)
    
    dtend_dt = None
    if dtend:
        try:
            if "T" in dtend:
                dtend_dt = datetime.fromisoformat(dtend.replace("Z", "+00:00"))
                if dtend_dt.tzinfo is None:
                    dtend_dt = dtend_dt.replace(tzinfo=client_tz)
            else:
                dtend_dt = datetime.strptime(dtend, "%Y-%m-%d").replace(tzinfo=client_tz)
        except ValueError:
            dtend_dt = None
    
    if is_all_day and not dtend_dt:
        dtend_dt = dtstart_dt + timedelta(days=1)
    elif not is_all_day and not dtend_dt:
        dtend_dt = dtstart_dt + timedelta(hours=1)
    
    dtend_utc = dtend_dt.astimezone(timezone.utc).replace(tzinfo=None) if dtend_dt else None
    
    rrule = None
    until_dt = None
    if rrule_freq and rrule_freq != "none":
        try:
            until_dt = datetime.fromisoformat(rrule_until.replace("Z", "+00:00"))
            if until_dt.tzinfo is None:
                until_dt = until_dt.replace(tzinfo=client_tz)
            until_dt = until_dt.astimezone(timezone.utc).replace(tzinfo=None)
        except:
            until_dt = datetime.strptime(rrule_until, "%Y-%m-%d")
    
    rrule = build_rrule(
        freq=rrule_freq,
        interval=rrule_interval,
        count=rrule_count,
        until=until_dt,
    )
    
    await event_service.create_event(
        calendar_id=calendar_id,
        summary=summary,
        description=description,
        dtstart=dtstart_utc,
        dtend=dtend_utc,
        location=location,
        rrule=rrule,
        is_all_day=is_all_day,
        color=color,
        timezone=tz,
    )
    
    response = HTMLResponse(content="<script>closeModal(); refreshCalendar();</script>")
    response.headers["HX-Trigger"] = "eventCreated"
    return response


@router.put("/calendar/events/{event_id}")
async def update_event(
    event_id: int,
    calendar_id: int = Form(...),
    summary: str = Form(...),
    dtstart: str = Form(...),
    dtend: Optional[str] = Form(None),
    is_all_day: bool = Form(False),
    location: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    color: Optional[str] = Form(None),
    rrule_freq: Optional[str] = Form(None),
    rrule_interval: int = Form(1),
    rrule_count: Optional[int] = Form(None),
    rrule_until: Optional[str] = Form(None),
    tz: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    event_service = EventService(db)
    
    if not await event_service.can_edit_event(event_id, user.id):
        raise HTTPException(status_code=403, detail="Cannot edit this event")
    
    writable_ids = await event_service.get_writable_calendars(user.id)
    if calendar_id not in writable_ids:
        raise HTTPException(status_code=403, detail="Cannot move event to this calendar")
    
    # Empty/whitespace tz must collapse to None (see create_event).
    tz = (tz or "").strip() or None
    client_tz = ZoneInfo(tz) if tz else timezone.utc
    
    try:
        if "T" in dtstart:
            dtstart_dt = datetime.fromisoformat(dtstart.replace("Z", "+00:00"))
            if dtstart_dt.tzinfo is None:
                dtstart_dt = dtstart_dt.replace(tzinfo=client_tz)
        else:
            dtstart_dt = datetime.strptime(dtstart, "%Y-%m-%d").replace(tzinfo=client_tz)
    except ValueError:
        dtstart_dt = datetime.now(client_tz)
    
    dtstart_utc = dtstart_dt.astimezone(timezone.utc).replace(tzinfo=None)
    
    dtend_dt = None
    if dtend:
        try:
            if "T" in dtend:
                dtend_dt = datetime.fromisoformat(dtend.replace("Z", "+00:00"))
                if dtend_dt.tzinfo is None:
                    dtend_dt = dtend_dt.replace(tzinfo=client_tz)
            else:
                dtend_dt = datetime.strptime(dtend, "%Y-%m-%d").replace(tzinfo=client_tz)
        except ValueError:
            dtend_dt = None
    
    if is_all_day and not dtend_dt:
        dtend_dt = dtstart_dt + timedelta(days=1)
    elif not is_all_day and not dtend_dt:
        dtend_dt = dtstart_dt + timedelta(hours=1)
    
    dtend_utc = dtend_dt.astimezone(timezone.utc).replace(tzinfo=None) if dtend_dt else None
    
    rrule = None
    until_dt = None
    if rrule_freq and rrule_freq != "none":
        try:
            until_dt = datetime.fromisoformat(rrule_until.replace("Z", "+00:00"))
            if until_dt.tzinfo is None:
                until_dt = until_dt.replace(tzinfo=client_tz)
            until_dt = until_dt.astimezone(timezone.utc).replace(tzinfo=None)
        except:
            until_dt = datetime.strptime(rrule_until, "%Y-%m-%d")
    
    rrule = build_rrule(
        freq=rrule_freq,
        interval=rrule_interval,
        count=rrule_count,
        until=until_dt,
    )
    
    event = await event_service.get_by_id(event_id)
    if event and event.calendar_id != calendar_id:
        event.calendar_id = calendar_id
        await db.commit()
    
    await event_service.update_event(
        event_id=event_id,
        summary=summary,
        description=description,
        dtstart=dtstart_utc,
        dtend=dtend_utc,
        location=location,
        rrule=rrule,
        is_all_day=is_all_day,
        color=color,
        timezone=tz,
    )
    
    return HTMLResponse(content="<script>closeModal(); refreshCalendar();</script>")


@router.patch("/calendar/events/{event_id}/drop", response_class=JSONResponse)
async def drop_event(
    event_id: int,
    start: str = Body(...),
    end: Optional[str] = Body(None),
    all_day: bool = Body(False),
    tz: Optional[str] = Body(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    """Timing-only update for FullCalendar drag-and-drop / resize.

    Preserves summary, description, location, color, and rrule. Recurring
    events are marked non-editable client-side (see calendar.html) because
    moving a single rrule-expanded occurrence would silently mutate the
    whole series — exception handling is a separate feature.
    """
    event_service = EventService(db)

    if not await event_service.can_edit_event(event_id, user.id):
        raise HTTPException(status_code=403, detail="Cannot edit this event")

    # Empty/whitespace tz must collapse to None (see update_event).
    tz = (tz or "").strip() or None
    client_tz = ZoneInfo(tz) if tz else timezone.utc

    def _parse_dt(s: Optional[str]) -> Optional[datetime]:
        if not s:
            return None
        try:
            if "T" in s:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=client_tz)
            else:
                # Date-only string (all-day drop in month view)
                dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=client_tz)
            return dt
        except ValueError:
            return None

    dtstart_dt = _parse_dt(start)
    if dtstart_dt is None:
        raise HTTPException(status_code=400, detail="Invalid start")

    dtend_dt = _parse_dt(end)
    if all_day and not dtend_dt:
        dtend_dt = dtstart_dt + timedelta(days=1)
    elif not all_day and not dtend_dt:
        dtend_dt = dtstart_dt + timedelta(hours=1)

    dtstart_utc = dtstart_dt.astimezone(timezone.utc).replace(tzinfo=None)
    dtend_utc = dtend_dt.astimezone(timezone.utc).replace(tzinfo=None) if dtend_dt else None

    await event_service.update_event(
        event_id=event_id,
        dtstart=dtstart_utc,
        dtend=dtend_utc,
        is_all_day=all_day,
        timezone=tz,
    )

    return JSONResponse(content={"ok": True})


@router.delete("/calendar/events/{event_id}")
async def delete_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    event_service = EventService(db)
    
    if not await event_service.can_edit_event(event_id, user.id):
        raise HTTPException(status_code=403, detail="Cannot delete this event")
    
    await event_service.delete(event_id)
    
    return HTMLResponse(content="<script>closeModal(); refreshCalendar();</script>")


@router.get("/calendar/export/{calendar_id}")
async def export_calendar(
    calendar_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    event_service = EventService(db)
    accessible_ids = await event_service.get_user_accessible_calendars(user.id)
    
    if calendar_id not in accessible_ids:
        raise HTTPException(status_code=403, detail="Cannot export this calendar")
    
    result = await db.execute(
        select(Calendar).where(Calendar.id == calendar_id)
    )
    calendar = result.scalar_one_or_none()
    if not calendar:
        raise HTTPException(status_code=404, detail="Calendar not found")
    
    result = await db.execute(
        select(Event).where(Event.calendar_id == calendar_id)
    )
    events = list(result.scalars().all())
    
    ics_content = generate_calendar_ics(events, calendar.name, calendar.color)
    
    return FastAPIResponse(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{calendar.name}.ics"',
        },
    )


@router.get("/calendar/import", response_class=HTMLResponse)
async def import_modal(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    event_service = EventService(db)
    writable_ids = await event_service.get_writable_calendars(user.id)
    
    result = await db.execute(
        select(Calendar).where(Calendar.id.in_(writable_ids))
    )
    calendars = result.scalars().all()
    
    return templates.TemplateResponse(
        "partials/import_modal.html",
        {
            "request": request,
            "user": user,
            "calendars": calendars,
        },
    )


@router.post("/calendar/import")
async def import_ics(
    calendar_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_session),
):
    event_service = EventService(db)
    writable_ids = await event_service.get_writable_calendars(user.id)
    
    if calendar_id not in writable_ids:
        raise HTTPException(status_code=403, detail="Cannot import into this calendar")
    
    if not file.filename.endswith(('.ics', '.ical', '.ifb', '.icalendar')):
        return HTMLResponse(content='<div class="p-4 text-red-600">Please upload a valid .ics file.</div>')
    
    try:
        content = await file.read()
        ics_content = content.decode("utf-8")
    except Exception:
        return HTMLResponse(content='<div class="p-4 text-red-600">Failed to read the file. Please try again.</div>')
    
    try:
        events_data = parse_ics_bulk(ics_content)
    except Exception as e:
        import logging
        logging.error(f"ICS parse error: {e}")
        return HTMLResponse(content=f'<div class="p-4 text-red-600">Failed to parse ICS file: {str(e)}</div>')
    
    if not events_data:
        return HTMLResponse(content='<div class="p-4 text-yellow-600">No events found in the ICS file.</div>')
    
    count = await event_service.import_events(calendar_id, events_data)
    
    return HTMLResponse(content=f'''<div class="p-4 text-green-600">
        <p class="font-semibold">Import complete!</p>
        <p>Successfully imported {count} event{"s" if count != 1 else ""}.</p>
    </div>
    <script>closeModal(); refreshCalendar();</script>''')
