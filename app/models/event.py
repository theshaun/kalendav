from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.calendar import Calendar


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    calendar_id: Mapped[int] = mapped_column(ForeignKey("calendars.id"), nullable=False, index=True)
    uid: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    dtstart: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    dtend: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rrule: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_ics: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    calendar: Mapped["Calendar"] = relationship("Calendar", back_populates="events")
    
    __table_args__ = (
        Index("ix_events_calendar_uid", "calendar_id", "uid", unique=True),
    )
