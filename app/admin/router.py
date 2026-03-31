from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import User, Calendar, Event, CalendarShare, APIKey
from app.schemas import (
    UserCreate, UserUpdate, UserResponse,
    CalendarCreate, CalendarUpdate, CalendarResponse,
    CalendarShareCreate, CalendarShareResponse,
    APIKeyCreate, APIKeyResponse,
)
from app.auth import get_current_user, hash_password, generate_api_key, hash_api_key
from fastapi.templating import Jinja2Templates
from datetime import datetime
import json
from typing import Optional

router = APIRouter()
templates = Jinja2Templates(directory="app/admin/templates")


def check_admin(user: User):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_admin(user)
    
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
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
    
    return RedirectResponse(url="/admin/users", status_code=303)


@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
async def edit_user_form(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
):
    check_admin(user)
    
    result = await db.execute(
        select(CalendarShare)
        .where(CalendarShare.calendar_id == calendar_id, CalendarShare.user_id == user_id)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        existing.permission = permission
    else:
        share = CalendarShare(
            calendar_id=calendar_id,
            user_id=user_id,
            permission=permission,
        )
        db.add(share)
    
    await db.commit()
    
    return RedirectResponse(url=f"/admin/calendars/{calendar_id}/shares", status_code=303)


@router.post("/shares/{share_id}/delete")
async def delete_share(
    share_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
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
    name: str = Form(...),
    user_id: int = Form(...),
    expires_at: str = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
):
    check_admin(user)
    
    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()
    
    if api_key:
        await db.delete(api_key)
        await db.commit()
    
    return RedirectResponse(url="/admin/api-keys", status_code=303)
