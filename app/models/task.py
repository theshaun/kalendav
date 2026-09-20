import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.calendar import Calendar


class TaskStatus(str, enum.Enum):
    NEEDS_ACTION = "NEEDS-ACTION"
    COMPLETED = "COMPLETED"
    IN_PROCESS = "IN-PROCESS"
    CANCELLED = "CANCELLED"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    calendar_id: Mapped[int] = mapped_column(ForeignKey("calendars.id"), nullable=False, index=True)
    uid: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="NEEDS-ACTION")
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    percent_complete: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    raw_ics: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    calendar: Mapped["Calendar"] = relationship("Calendar", back_populates="tasks")

    __table_args__ = (
        Index("ix_tasks_calendar_uid", "calendar_id", "uid", unique=True),
    )
