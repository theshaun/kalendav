from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.calendar import Calendar
    from app.models.share import CalendarShare
    from app.models.api_key import APIKey


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    calendars: Mapped[list["Calendar"]] = relationship("Calendar", back_populates="user", cascade="all, delete-orphan")
    shares: Mapped[list["CalendarShare"]] = relationship("CalendarShare", back_populates="user", cascade="all, delete-orphan")
    api_keys: Mapped[list["APIKey"]] = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
