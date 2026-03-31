from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response as FastAPIResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import User, Calendar, Event, APIKey, CalendarShare
from app.auth import verify_password, hash_api_key
from datetime import datetime
import hashlib

router = APIRouter()


async def authenticate_ics_feed(
    request: Request,
    api_key: str = Query(None),
    credentials: HTTPBasicCredentials = Depends(HTTPBasic(auto_error=False)),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, Calendar]:
    user = None
    
    if api_key:
        key_hash = hash_api_key(api_key)
        result = await db.execute(
            select(APIKey)
            .options(selectinload(APIKey.user))
            .where(APIKey.key_hash == key_hash, APIKey.is_active == True)
        )
        api_key_obj = result.scalar_one_or_none()
        
        if not api_key_obj:
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        if api_key_obj.expires_at and api_key_obj.expires_at < datetime.utcnow():
            raise HTTPException(status_code=401, detail="API key expired")
        
        user = api_key_obj.user
    
    elif credentials:
        result = await db.execute(
            select(User).where(User.username == credentials.username)
        )
        user = result.scalar_one_or_none()
        
        if not user or not verify_password(credentials.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
    
    else:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    return user, db


@router.get("/{calendar_id}")
async def get_ics_feed(
    calendar_id: int,
    request: Request,
    api_key: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    user, db = await authenticate_ics_feed(request, api_key, db=db)
    
    result = await db.execute(
        select(Calendar)
        .options(selectinload(Calendar.shares))
        .where(Calendar.id == calendar_id)
    )
    calendar = result.scalar_one_or_none()
    
    if not calendar:
        raise HTTPException(status_code=404, detail="Calendar not found")
    
    if calendar.user_id != user.id:
        has_access = any(share.user_id == user.id for share in calendar.shares)
        if not has_access:
            raise HTTPException(status_code=403, detail="Access denied")
    
    result = await db.execute(
        select(Event).where(Event.calendar_id == calendar.id)
    )
    events = result.scalars().all()
    
    from app.caldav.ics_parser import generate_calendar_ics
    ics_content = generate_calendar_ics(events, calendar.name)
    
    return FastAPIResponse(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{calendar.name}.ics"',
            "Cache-Control": "no-cache",
        },
    )
