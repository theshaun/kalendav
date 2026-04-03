from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    is_admin: Optional[bool] = None


class UserResponse(UserBase):
    id: int
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CalendarBase(BaseModel):
    name: str
    description: Optional[str] = None
    color: Optional[str] = "#3B82F6"


class CalendarCreate(CalendarBase):
    pass


class CalendarUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None


class CalendarResponse(CalendarBase):
    id: int
    user_id: int
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True


class EventBase(BaseModel):
    summary: Optional[str] = None
    description: Optional[str] = None
    dtstart: datetime
    dtend: Optional[datetime] = None
    is_all_day: bool = False
    location: Optional[str] = None


class EventCreate(EventBase):
    uid: str
    raw_ics: str
    rrule: Optional[str] = None


class EventUpdate(BaseModel):
    summary: Optional[str] = None
    description: Optional[str] = None
    dtstart: Optional[datetime] = None
    dtend: Optional[datetime] = None
    is_all_day: Optional[bool] = None
    location: Optional[str] = None
    rrule: Optional[str] = None
    raw_ics: Optional[str] = None


class EventResponse(EventBase):
    id: int
    calendar_id: int
    uid: str
    rrule: Optional[str]
    raw_ics: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


from app.models.share import SharePermission


class CalendarShareCreate(BaseModel):
    user_id: int
    permission: str


class CalendarShareResponse(BaseModel):
    id: int
    calendar_id: int
    user_id: int
    permission: str
    created_at: datetime

    class Config:
        from_attributes = True


class APIKeyCreate(BaseModel):
    name: str
    permissions: Optional[dict] = None
    expires_at: Optional[datetime] = None


class APIKeyResponse(BaseModel):
    id: int
    name: str
    permissions: Optional[dict]
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime
    key: Optional[str] = None

    class Config:
        from_attributes = True
