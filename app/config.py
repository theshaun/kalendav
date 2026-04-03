from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "KalenDAV"
    debug: bool = False
    
    database_url: str = "sqlite+aiosqlite:///./caldav.db"
    
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 30
    
    admin_user: str = "admin"
    admin_password: str = "admin"
    
    base_uri: str = "http://localhost:8000"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
