import enum
from sqlalchemy import String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.calendar import Calendar


class SharePermission(str, enum.Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class CalendarShare(Base):
    __tablename__ = "calendar_shares"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    calendar_id: Mapped[int] = mapped_column(ForeignKey("calendars.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    permission: Mapped[SharePermission] = mapped_column(Enum(SharePermission), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    calendar: Mapped["Calendar"] = relationship("Calendar", back_populates="shares")
    user: Mapped["User"] = relationship("User", back_populates="shares")
