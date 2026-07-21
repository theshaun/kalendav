from pydantic_settings import BaseSettings
from typing import Optional
from zoneinfo import ZoneInfo, available_timezones
from fastapi import Request


def _validate_timezone(v: str) -> str:
    # Empty / unknown -> fall back to UTC rather than crash at boot.
    if not v or v not in available_timezones():
        return "UTC"
    return v


class Settings(BaseSettings):
    app_name: str = "KalenDAV"
    debug: bool = False
    
    database_url: str = "sqlite+aiosqlite:///./caldav.db"
    
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 30
    
    admin_user: str = "admin"
    admin_password: str = "admin"
    
    base_uri: str = "http://localhost:8000"

    # IANA timezone (e.g. "Australia/Brisbane") applied to naive datetimes
    # when serializing ICS feeds. UTC is the safe default.
    default_timezone: str = "UTC"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def tz(self) -> ZoneInfo:
        """Resolved ZoneInfo for default_timezone (always valid)."""
        return ZoneInfo(_validate_timezone(self.default_timezone))


settings = Settings()


def get_base_uri(request: Request) -> str:
    base = settings.base_uri.rstrip("/")
    if not base or base.endswith("localhost:8000"):
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        if host:
            base = f"{proto}://{host}"
    return base
