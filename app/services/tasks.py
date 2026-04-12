from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import FlagReason, TaskStatus
from app.models import Task, User
from app.services.audit import write_audit


async def create_task(session: AsyncSession, *, client_id: int, created_by: int, description: str, assigned_to: int | None = None) -> Task:
    task = Task(client_id=client_id, created_by=created_by, description=description, assigned_to=assigned_to)
    session.add(task)
    await session.flush()
    await write_audit(session, client_id=client_id, actor_id=created_by, action='task_created', entity_type='task', entity_id=task.id, details={'assigned_to': assigned_to})
    return task


async def list_open_tasks(session: AsyncSession, *, client_id: int, include_done: bool = False) -> list[Task]:
    stmt = select(Task).where(Task.client_id == client_id)
    if not include_done:
        stmt = stmt.where(Task.status.in_([TaskStatus.OPEN, TaskStatus.FLAGGED]))
    stmt = stmt.order_by(Task.created_at.asc())
    return list((await session.scalars(stmt)).all())


async def complete_task(session: AsyncSession, *, client_id: int, task_id: int, actor_id: int) -> Task | None:
    task = await session.scalar(select(Task).where(Task.client_id == client_id, Task.id == task_id))
    if not task:
        return None
    task.status = TaskStatus.DONE
    task.completed_at = datetime.utcnow()
    await session.flush()
    await write_audit(session, client_id=client_id, actor_id=actor_id, action='task_done', entity_type='task', entity_id=task.id)
    return task


async def flag_task(session: AsyncSession, *, client_id: int, task_id: int, actor_id: int, reason: FlagReason, note: str | None) -> Task | None:
    task = await session.scalar(select(Task).where(Task.client_id == client_id, Task.id == task_id))
    if not task:
        return None
    task.status = TaskStatus.FLAGGED
    task.flag_reason = reason
    task.flag_note = note
    await session.flush()
    await write_audit(session, client_id=client_id, actor_id=actor_id, action='task_flagged', entity_type='task', entity_id=task.id, details={'reason': reason.value, 'note': note})
    return task


async def assign_task(session: AsyncSession, *, client_id: int, task_id: int, actor_id: int, assigned_to: int) -> Task | None:
    task = await session.scalar(select(Task).where(Task.client_id == client_id, Task.id == task_id))
    if not task:
        return None
    task.assigned_to = assigned_to
    task.status = TaskStatus.OPEN
    await session.flush()
    await write_audit(session, client_id=client_id, actor_id=actor_id, action='task_assigned', entity_type='task', entity_id=task.id, details={'assigned_to': assigned_to})
    return task


async def overdue_tasks(session: AsyncSession, *, client_id: int) -> list[Task]:
    threshold = datetime.utcnow() - timedelta(hours=48)
    rows = await session.scalars(select(Task).where(Task.client_id == client_id, Task.status == TaskStatus.OPEN, Task.created_at <= threshold).order_by(Task.created_at.asc()))
    return list(rows.all())


async def flagged_tasks(session: AsyncSession, *, client_id: int) -> list[Task]:
    rows = await session.scalars(select(Task).where(Task.client_id == client_id, Task.status == TaskStatus.FLAGGED).order_by(Task.created_at.asc()))
    return list(rows.all())


async def task_counts(session: AsyncSession, *, client_id: int) -> tuple[int, int]:
    open_q = await session.execute(select(func.count(Task.id)).where(Task.client_id == client_id, Task.status == TaskStatus.OPEN))
    flagged_q = await session.execute(select(func.count(Task.id)).where(Task.client_id == client_id, Task.status == TaskStatus.FLAGGED))
    return int(open_q.scalar() or 0), int(flagged_q.scalar() or 0)


async def user_map(session: AsyncSession, *, client_id: int) -> dict[int, str]:
    users = await session.scalars(select(User).where(User.client_id == client_id))
    return {u.id: u.display_name for u in users.all()}
