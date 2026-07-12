from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from app.models import Event, Calendar, CalendarShare
from app.models.share import SharePermission
from datetime import datetime
from typing import Optional, List, Sequence
import uuid


class EventService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, event_id: int) -> Optional[Event]:
        result = await self.db.execute(
            select(Event).options(selectinload(Event.calendar)).where(Event.id == event_id)
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
    ) -> Sequence[Event]:
        query = select(Event).where(Event.calendar_id == calendar_id)

        if start:
            query = query.where(Event.dtstart >= start)
        if end:
            query = query.where(Event.dtend <= end)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_user_accessible_calendars(self, user_id: int) -> List[int]:
        owned = await self.db.execute(
            select(Calendar.id).where(Calendar.user_id == user_id)
        )
        calendar_ids = [c[0] for c in owned.fetchall()]
        
        shared = await self.db.execute(
            select(CalendarShare.calendar_id).where(
                CalendarShare.user_id == user_id,
                CalendarShare.permission.in_([SharePermission.READ, SharePermission.WRITE, SharePermission.ADMIN])
            )
        )
        calendar_ids.extend([s[0] for s in shared.fetchall()])
        
        return list(set(calendar_ids))

    async def get_writable_calendars(self, user_id: int) -> List[int]:
        owned = await self.db.execute(
            select(Calendar.id).where(Calendar.user_id == user_id)
        )
        calendar_ids = [c[0] for c in owned.fetchall()]
        
        shared = await self.db.execute(
            select(CalendarShare.calendar_id).where(
                CalendarShare.user_id == user_id,
                CalendarShare.permission.in_([SharePermission.WRITE, SharePermission.ADMIN])
            )
        )
        calendar_ids.extend([s[0] for s in shared.fetchall()])
        
        return list(set(calendar_ids))

    async def get_events_for_user(
        self,
        user_id: int,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Sequence[Event]:
        calendar_ids = await self.get_user_accessible_calendars(user_id)
        if not calendar_ids:
            return []
        
        query = select(Event).options(
            selectinload(Event.calendar).selectinload(Calendar.user)
        ).where(Event.calendar_id.in_(calendar_ids))
        
        if start:
            query = query.where(Event.dtend >= start)
        if end:
            query = query.where(Event.dtstart <= end)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def can_access_event(self, event_id: int, user_id: int) -> bool:
        event = await self.get_by_id(event_id)
        if not event:
            return False
        
        accessible_ids = await self.get_user_accessible_calendars(user_id)
        return event.calendar_id in accessible_ids

    async def can_edit_event(self, event_id: int, user_id: int) -> bool:
        event = await self.get_by_id(event_id)
        if not event:
            return False
        
        writable_ids = await self.get_writable_calendars(user_id)
        return event.calendar_id in writable_ids

    async def create_event(
        self,
        calendar_id: int,
        summary: str,
        dtstart: datetime,
        dtend: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        rrule: Optional[str] = None,
        is_all_day: bool = False,
        color: Optional[str] = None,
        timezone: Optional[str] = None,
    ) -> Event:
        uid = str(uuid.uuid4())

        from app.caldav.ics_parser import generate_ics
        raw_ics = generate_ics(
            uid=uid,
            summary=summary,
            dtstart=dtstart,
            dtend=dtend,
            description=description,
            location=location,
            rrule=rrule,
            is_all_day=is_all_day,
            color=color,
            timezone=timezone,
        )

        event = Event(
            calendar_id=calendar_id,
            uid=uid,
            summary=summary,
            description=description,
            dtstart=dtstart,
            dtend=dtend,
            location=location,
            color=color,
            rrule=rrule,
            timezone=timezone,
            raw_ics=raw_ics,
            is_all_day=is_all_day,
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def update_event(
        self,
        event_id: int,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        dtstart: Optional[datetime] = None,
        dtend: Optional[datetime] = None,
        location: Optional[str] = None,
        rrule: Optional[str] = None,
        is_all_day: Optional[bool] = None,
        color: Optional[str] = ...,
        timezone: Optional[str] = None,
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
        if is_all_day is not None:
            event.is_all_day = is_all_day
        if color is not ...:
            event.color = color
        if timezone is not None:
            event.timezone = timezone

        from app.caldav.ics_parser import generate_ics
        event.raw_ics = generate_ics(
            uid=event.uid,
            summary=event.summary or "",
            dtstart=event.dtstart,
            dtend=event.dtend,
            description=event.description,
            location=event.location,
            rrule=event.rrule,
            is_all_day=event.is_all_day,
            color=event.color,
            timezone=event.timezone,
        )

        event.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(event)
        return event

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
        color: Optional[str] = None,
    ) -> Event:
        event = Event(
            calendar_id=calendar_id,
            uid=uid,
            summary=summary,
            description=description,
            dtstart=dtstart or datetime.utcnow(),
            dtend=dtend,
            location=location,
            color=color,
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
        color: Optional[str] = None,
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
        if color is not None:
            event.color = color

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

    async def import_events(self, calendar_id: int, events_data: list) -> int:
        count = 0
        for event_data in events_data:
            event = Event(
                calendar_id=calendar_id,
                uid=event_data["uid"],
                summary=event_data.get("summary"),
                description=event_data.get("description"),
                dtstart=event_data.get("dtstart", datetime.utcnow()),
                dtend=event_data.get("dtend"),
                location=event_data.get("location"),
                color=event_data.get("color"),
                rrule=event_data.get("rrule"),
                is_all_day=event_data.get("is_all_day", False),
                raw_ics=event_data.get("raw_ics", ""),
            )
            self.db.add(event)
            count += 1
        await self.db.commit()
        return count
