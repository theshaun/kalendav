from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
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
from fastapi.templating import Jinja2Templates
from datetime import datetime
import json
from typing import Optional

router = APIRouter()
templates = Jinja2Templates(directory="app/admin/templates")


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
        color="#3B82F6",
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
    color: str = Form("#3B82F6"),
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
    calendars = result.scalars().all()
    
    return templates.TemplateResponse(
        "user_calendars.html",
        {"request": request, "user": user, "calendars": calendars},
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
    color: str = Form("#3B82F6"),
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
    color: str = Form("#3B82F6"),
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
