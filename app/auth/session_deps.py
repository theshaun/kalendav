from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import User
from app.auth.session import get_session_user_id
from typing import Optional


class LoginRequiredException(Exception):
    pass


async def get_current_user_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    user_id = get_session_user_id(request)
    
    if not user_id:
        raise LoginRequiredException()
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise LoginRequiredException()
    
    return user


async def get_current_user_session_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    user_id = get_session_user_id(request)
    
    if not user_id:
        return None
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    return user
