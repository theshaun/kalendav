from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response as FastAPIResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models import User, Calendar, Event, APIKey, CalendarShare
from app.auth import verify_password, hash_api_key
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter()
_security = HTTPBasic(auto_error=False)


async def authenticate_ics_feed(
    request: Request,
    api_key: str = Query(None),
    credentials: HTTPBasicCredentials = Depends(_security),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, AsyncSession]:
    calendar_id = request.path_params.get("calendar_id", "?")

    # Extract api_key from multiple auth surfaces TRMNL and other clients use.
    # Precedence: query param > X-API-Key header > Authorization: Bearer.
    header_key = request.headers.get("x-api-key")
    bearer_key = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        bearer_key = auth_header[7:].strip()

    resolved_key = api_key or header_key or bearer_key
    auth_method = (
        "query" if api_key else
        "x-api-key" if header_key else
        "bearer" if bearer_key else
        "basic" if credentials else
        "none"
    )

    user = None

    if resolved_key:
        key_hash = hash_api_key(resolved_key)
        result = await db.execute(
            select(APIKey)
            .options(selectinload(APIKey.user))
            .where(APIKey.key_hash == key_hash, APIKey.is_active == True)
        )
        api_key_obj = result.scalar_one_or_none()

        if not api_key_obj:
            logger.info(
                "ics auth fail calendar_id=%s method=%s reason=invalid_key",
                calendar_id, auth_method,
            )
            raise HTTPException(status_code=401, detail="Invalid API key")

        if api_key_obj.expires_at and api_key_obj.expires_at < datetime.utcnow():
            logger.info(
                "ics auth fail calendar_id=%s method=%s reason=expired user_id=%s",
                calendar_id, auth_method, api_key_obj.user_id,
            )
            raise HTTPException(status_code=401, detail="API key expired")

        user = api_key_obj.user

    elif credentials:
        result = await db.execute(
            select(User).where(User.username == credentials.username)
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(credentials.password, user.password_hash):
            logger.info(
                "ics auth fail calendar_id=%s method=basic reason=invalid_credentials",
                calendar_id,
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")

    else:
        logger.info(
            "ics auth fail calendar_id=%s method=none reason=no_credentials",
            calendar_id,
        )
        raise HTTPException(status_code=401, detail="Authentication required")

    logger.info(
        "ics auth ok calendar_id=%s method=%s user_id=%s",
        calendar_id, auth_method, user.id,
    )
    return user, db


@router.get("/{calendar_id}")
async def get_ics_feed(
    calendar_id: int,
    auth: tuple[User, AsyncSession] = Depends(authenticate_ics_feed),
):
    user, db = auth

    result = await db.execute(
        select(Calendar)
        .options(selectinload(Calendar.shares))
        .where(Calendar.id == calendar_id)
    )
    calendar = result.scalar_one_or_none()

    if not calendar:
        logger.info(
            "ics not_found calendar_id=%s user_id=%s",
            calendar_id, user.id,
        )
        raise HTTPException(status_code=404, detail="Calendar not found")

    if calendar.user_id != user.id:
        has_access = any(share.user_id == user.id for share in calendar.shares)
        if not has_access:
            logger.warning(
                "ics access_denied calendar_id=%s owner_id=%s requesting_user_id=%s",
                calendar_id, calendar.user_id, user.id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "access_denied",
                    "calendar_id": calendar_id,
                    "requesting_user_id": user.id,
                    "hint": (
                        "API key authenticated but its owner has no share on this "
                        "calendar. Verify the calendar_id in the URL matches a "
                        "calendar owned by or shared with the API key owner."
                    ),
                },
            )

    result = await db.execute(
        select(Event).where(Event.calendar_id == calendar.id)
    )
    events = result.scalars().all()

    from app.caldav.ics_parser import generate_calendar_ics
    ics_content = generate_calendar_ics(events, calendar.name, calendar.color)

    return FastAPIResponse(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{calendar.name}.ics"',
            "Cache-Control": "no-cache",
        },
    )
