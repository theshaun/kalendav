import uuid
from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.caldav.ics_parser import generate_vtodo
from app.models import Calendar, CalendarShare, Task
from app.models.share import SharePermission
from app.models.task import TaskStatus


class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, task_id: int) -> Optional[Task]:
        result = await self.db.execute(
            select(Task).options(selectinload(Task.calendar)).where(Task.id == task_id)
        )
        return result.scalar_one_or_none()

    async def get_by_uid(self, calendar_id: int, uid: str) -> Optional[Task]:
        result = await self.db.execute(
            select(Task).where(and_(Task.calendar_id == calendar_id, Task.uid == uid))
        )
        return result.scalar_one_or_none()

    async def get_by_calendar(self, calendar_id: int) -> Sequence[Task]:
        result = await self.db.execute(
            select(Task)
            .where(Task.calendar_id == calendar_id)
            .order_by(Task.sort_order.asc(), Task.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_tasks_for_user(self, user_id: int) -> Sequence[Task]:
        owned = await self.db.execute(
            select(Calendar.id).where(Calendar.user_id == user_id)
        )
        calendar_ids = [c[0] for c in owned.fetchall()]

        shared = await self.db.execute(
            select(CalendarShare.calendar_id).where(
                CalendarShare.user_id == user_id,
                CalendarShare.permission.in_(
                    [SharePermission.READ, SharePermission.WRITE, SharePermission.ADMIN]
                ),
            )
        )
        calendar_ids.extend([s[0] for s in shared.fetchall()])

        if not calendar_ids:
            return []

        result = await self.db.execute(
            select(Task)
            .where(Task.calendar_id.in_(list(set(calendar_ids))))
            .order_by(Task.sort_order.asc(), Task.created_at.asc())
        )
        return list(result.scalars().all())

    async def can_edit_task(self, task_id: int, user_id: int) -> bool:
        task = await self.get_by_id(task_id)
        if not task:
            return False

        owned = await self.db.execute(
            select(Calendar.id).where(Calendar.user_id == user_id)
        )
        writable_ids = [c[0] for c in owned.fetchall()]

        shared = await self.db.execute(
            select(CalendarShare.calendar_id).where(
                CalendarShare.user_id == user_id,
                CalendarShare.permission.in_(
                    [SharePermission.WRITE, SharePermission.ADMIN]
                ),
            )
        )
        writable_ids.extend([s[0] for s in shared.fetchall()])

        return task.calendar_id in set(writable_ids)

    async def create_task(
        self,
        calendar_id: int,
        summary: str,
        description: Optional[str] = None,
        due: Optional[datetime] = None,
        priority: Optional[int] = None,
        status: TaskStatus | str = TaskStatus.NEEDS_ACTION,
        timezone: Optional[str] = None,
        uid: Optional[str] = None,
    ) -> Task:
        uid = uid or str(uuid.uuid4())

        max_order = await self.db.execute(
            select(func.coalesce(func.max(Task.sort_order), -1)).where(
                Task.calendar_id == calendar_id
            )
        )
        sort_order = max_order.scalar_one() + 1

        status_str = (
            status.value if isinstance(status, TaskStatus) else (status or "NEEDS-ACTION")
        )

        raw_ics = generate_vtodo(
            uid=uid,
            summary=summary or "",
            status=status_str,
            description=description,
            priority=priority,
            due=due,
            percent_complete=None,
            timezone=timezone,
        )

        task = Task(
            calendar_id=calendar_id,
            uid=uid,
            summary=summary,
            description=description,
            status=status_str,
            priority=priority,
            due=due,
            sort_order=sort_order,
            raw_ics=raw_ics,
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def update_task(self, task_id: int, **fields) -> Optional[Task]:
        task = await self.get_by_id(task_id)
        if not task:
            return None

        if "summary" in fields:
            task.summary = fields["summary"]
        if "description" in fields:
            task.description = fields["description"]
        if "priority" in fields:
            task.priority = fields["priority"]
        if "due" in fields:
            task.due = fields["due"]
        if "completed" in fields:
            task.completed = fields["completed"]
        if "percent_complete" in fields:
            task.percent_complete = fields["percent_complete"]

        if "status" in fields and fields["status"] is not None:
            new_status = fields["status"]
            if isinstance(new_status, TaskStatus):
                new_status = new_status.value
            else:
                new_status = str(new_status)
            task.status = new_status
            if new_status == "COMPLETED":
                task.completed = datetime.utcnow()
                task.percent_complete = 100
            elif new_status == "NEEDS-ACTION":
                task.completed = None
                task.percent_complete = None

        task.raw_ics = generate_vtodo(
            uid=task.uid,
            summary=task.summary or "",
            status=task.status,
            description=task.description,
            priority=task.priority,
            due=task.due,
            completed=task.completed,
            percent_complete=task.percent_complete,
            timezone=None,
        )

        task.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def toggle(self, task_id: int) -> Optional[Task]:
        task = await self.get_by_id(task_id)
        if not task:
            return None
        if task.status == "COMPLETED":
            return await self.update_task(task_id, status="NEEDS-ACTION")
        return await self.update_task(task_id, status="COMPLETED")

    async def delete(self, task_id: int) -> bool:
        task = await self.get_by_id(task_id)
        if not task:
            return False
        await self.db.delete(task)
        await self.db.commit()
        return True

    async def reorder(self, ordered_task_ids: list[int]) -> None:
        for index, task_id in enumerate(ordered_task_ids):
            task = await self.get_by_id(task_id)
            if task is not None:
                task.sort_order = index
        await self.db.commit()
