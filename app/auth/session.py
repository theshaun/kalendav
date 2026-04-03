from fastapi import Request
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer
from app.config import settings
from typing import Optional

serializer = URLSafeTimedSerializer(settings.secret_key, salt="admin-session")
SESSION_COOKIE_NAME = "admin_session"


def create_session(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})


def get_session_user_id(request: Request) -> Optional[int]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    
    try:
        data = serializer.loads(token, max_age=3600 * 24)
        return data.get("user_id")
    except Exception:
        return None


def set_session_cookie(response: RedirectResponse, user_id: int) -> RedirectResponse:
    token = create_session(user_id)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=3600 * 24,
        samesite="lax",
    )
    return response


def clear_session_cookie(response: RedirectResponse) -> RedirectResponse:
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
