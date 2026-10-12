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
            .options(selectinload(Task.calendar))
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
        related_to: Optional[str] = None,
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
            related_to=related_to,
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
            related_to=related_to,
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
        if "related_to" in fields:
            task.related_to = fields["related_to"]

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
            related_to=task.related_to,
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

    async def move_task(self, task_id: int, target_calendar_id: int) -> Optional[Task]:
        """Move a task to another calendar, appending at its bottom.

        Keeps uid and related_to; a relation pointing at the old calendar's
        task renders top-level until re-parented. Returns None when the task
        or target calendar does not exist.
        """
        task = await self.get_by_id(task_id)
        if task is None:
            return None
        target = await self.db.execute(
            select(Calendar.id).where(Calendar.id == target_calendar_id)
        )
        if target.scalar_one_or_none() is None:
            return None
        max_order = await self.db.execute(
            select(func.coalesce(func.max(Task.sort_order), -1)).where(
                Task.calendar_id == target_calendar_id
            )
        )
        task.calendar_id = target_calendar_id
        task.sort_order = max_order.scalar_one() + 1
        task.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def delete(self, task_id: int) -> bool:
        task = await self.get_by_id(task_id)
        if not task:
            return False
        await self.db.delete(task)
        await self.db.commit()
        return True

    async def reorder(self, ordered_task_ids: list[int]) -> None:
        # sort_order is a per-calendar sequence: number each task by its
        # position among its own calendar's tasks in the submitted order.
        next_index: dict[int, int] = {}
        for task_id in ordered_task_ids:
            task = await self.get_by_id(task_id)
            if task is None:
                continue
            task.sort_order = next_index.get(task.calendar_id, 0)
            next_index[task.calendar_id] = task.sort_order + 1
        await self.db.commit()

    async def apply_parents(self, parent_by_id: dict[int, int]) -> None:
        """Set related_to from task-id -> parent-task-id (0/None = top-level).

        Parent must live in the same calendar; foreign or missing parents
        clear the relation. After applying, any task on a related_to cycle
        has its own link broken so every member falls back to top-level.
        """
        if not parent_by_id:
            return

        result = await self.db.execute(select(Task).where(Task.id.in_(parent_by_id)))
        touched = [t for t in result.scalars().all() if t is not None]
        if not touched:
            return

        cal_ids = {t.calendar_id for t in touched}
        result = await self.db.execute(
            select(Task).where(Task.calendar_id.in_(cal_ids))
        )
        scope = list(result.scalars().all())
        by_id = {t.id: t for t in scope}
        by_uid: dict[tuple[int, str], Task] = {}
        for t in scope:
            by_uid.setdefault((t.calendar_id, t.uid), t)

        for task in touched:
            parent_id = parent_by_id.get(task.id) or None
            parent = by_id.get(parent_id) if parent_id else None
            valid = parent is not None and parent is not task and parent.calendar_id == task.calendar_id
            task.related_to = parent.uid if valid else None

        def on_cycle(task: Task) -> bool:
            seen: set[int] = set()
            cur = task
            while cur is not None and cur.related_to:
                if cur.id in seen:
                    return True
                seen.add(cur.id)
                cur = by_uid.get((cur.calendar_id, cur.related_to))
            return False

        for task in touched:
            if on_cycle(task):
                task.related_to = None

        for task in touched:
            task.raw_ics = generate_vtodo(
                uid=task.uid,
                summary=task.summary or "",
                status=task.status,
                description=task.description,
                priority=task.priority,
                due=task.due,
                completed=task.completed,
                percent_complete=task.percent_complete,
                related_to=task.related_to,
            )

        await self.db.commit()


def build_task_tree(tasks: Sequence[Task]) -> list[Task]:
    """Attach ``children`` lists and return top-level tasks in order.

    A task is a child when its ``related_to`` UID matches another task's UID
    in the SAME calendar (UIDs are only unique per calendar). Tasks whose
    parent is missing, foreign, or part of a cycle stay top-level.
    """
    for task in tasks:
        task.children = []

    by_uid: dict[tuple[int, str], list[Task]] = {}
    for task in tasks:
        by_uid.setdefault((task.calendar_id, task.uid), []).append(task)

    top_level: list[Task] = []
    placed: set[int] = set()

    def attach(task: Task, path: frozenset[int]) -> bool:
        # True => task ended up as someone's descendant (or already placed);
        # False => task must stay top-level (missing parent or cycle).
        if task.id in placed:
            return True
        if task.id in path:
            return False
        if task.related_to:
            for candidate in by_uid.get((task.calendar_id, task.related_to), []):
                if candidate is not task and attach(candidate, path | {task.id}):
                    candidate.children.append(task)
                    placed.add(task.id)
                    return True
        placed.add(task.id)
        top_level.append(task)
        return False

    for task in tasks:
        attach(task, frozenset())

    return top_level
