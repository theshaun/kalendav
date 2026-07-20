from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.event import Event
    from app.models.share import CalendarShare


class Calendar(Base):
    __tablename__ = "calendars"

    # Brand accent (Tailwind blue-500, DESIGN.md §2). Import this instead of
    # re-inlining the hex in router forms or templates.
    DEFAULT_COLOR = "#3B82F6"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(7), default=DEFAULT_COLOR)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    user: Mapped["User"] = relationship("User", back_populates="calendars")
    events: Mapped[list["Event"]] = relationship("Event", back_populates="calendar", cascade="all, delete-orphan")
    shares: Mapped[list["CalendarShare"]] = relationship("CalendarShare", back_populates="calendar", cascade="all, delete-orphan")
    
    @property
    def uid(self) -> str:
        return f"calendar-{self.id}"
