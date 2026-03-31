from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import Calendar, Event
from datetime import datetime
from typing import Optional, List


class CalendarService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, calendar_id: int) -> Optional[Calendar]:
        result = await self.db.execute(
            select(Calendar).where(Calendar.id == calendar_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user(self, user_id: int) -> List[Calendar]:
        result = await self.db.execute(
            select(Calendar).where(Calendar.user_id == user_id)
        )
        return result.scalars().all()

    async def create(
        self,
        user_id: int,
        name: str,
        description: Optional[str] = None,
        color: str = "#3B82F6",
    ) -> Calendar:
        calendar = Calendar(
            user_id=user_id,
            name=name,
            description=description,
            color=color,
        )
        self.db.add(calendar)
        await self.db.commit()
        await self.db.refresh(calendar)
        return calendar

    async def update(
        self,
        calendar_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Optional[Calendar]:
        calendar = await self.get_by_id(calendar_id)
        if not calendar:
            return None

        if name is not None:
            calendar.name = name
        if description is not None:
            calendar.description = description
        if color is not None:
            calendar.color = color

        await self.db.commit()
        await self.db.refresh(calendar)
        return calendar

    async def delete(self, calendar_id: int) -> bool:
        calendar = await self.get_by_id(calendar_id)
        if not calendar:
            return False

        await self.db.delete(calendar)
        await self.db.commit()
        return True
