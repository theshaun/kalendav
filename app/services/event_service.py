from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models import Event
from datetime import datetime
from typing import Optional, List


class EventService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, event_id: int) -> Optional[Event]:
        result = await self.db.execute(
            select(Event).where(Event.id == event_id)
        )
        return result.scalar_one_or_none()

    async def get_by_uid(self, calendar_id: int, uid: str) -> Optional[Event]:
        result = await self.db.execute(
            select(Event).where(
                and_(Event.calendar_id == calendar_id, Event.uid == uid)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_calendar(
        self,
        calendar_id: int,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[Event]:
        query = select(Event).where(Event.calendar_id == calendar_id)

        if start:
            query = query.where(Event.dtstart >= start)
        if end:
            query = query.where(Event.dtend <= end)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def create(
        self,
        calendar_id: int,
        uid: str,
        raw_ics: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        dtstart: Optional[datetime] = None,
        dtend: Optional[datetime] = None,
        location: Optional[str] = None,
        rrule: Optional[str] = None,
    ) -> Event:
        event = Event(
            calendar_id=calendar_id,
            uid=uid,
            summary=summary,
            description=description,
            dtstart=dtstart or datetime.utcnow(),
            dtend=dtend,
            location=location,
            rrule=rrule,
            raw_ics=raw_ics,
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def update(
        self,
        event_id: int,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        dtstart: Optional[datetime] = None,
        dtend: Optional[datetime] = None,
        location: Optional[str] = None,
        rrule: Optional[str] = None,
        raw_ics: Optional[str] = None,
    ) -> Optional[Event]:
        event = await self.get_by_id(event_id)
        if not event:
            return None

        if summary is not None:
            event.summary = summary
        if description is not None:
            event.description = description
        if dtstart is not None:
            event.dtstart = dtstart
        if dtend is not None:
            event.dtend = dtend
        if location is not None:
            event.location = location
        if rrule is not None:
            event.rrule = rrule
        if raw_ics is not None:
            event.raw_ics = raw_ics

        event.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def delete(self, event_id: int) -> bool:
        event = await self.get_by_id(event_id)
        if not event:
            return False

        await self.db.delete(event)
        await self.db.commit()
        return True
