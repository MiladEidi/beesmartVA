from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import TimesheetStatus
from app.models import HourLog, Timesheet, User
from app.services.audit import write_audit
from app.utils.dates import week_start_for


async def log_hours(session: AsyncSession, *, va_id: int, client_id: int, work_date: date, hours: Decimal, note: str | None) -> HourLog:
    log = HourLog(va_id=va_id, client_id=client_id, work_date=work_date, hours=hours, note=note)
    session.add(log)
    await session.flush()
    await write_audit(session, client_id=client_id, actor_id=va_id, action='hours_logged', entity_type='hour_log', entity_id=log.id, details={'work_date': work_date.isoformat(), 'hours': str(hours), 'note': note})
    return log


async def edit_hours(session: AsyncSession, *, va_id: int, client_id: int, work_date: date, hours: Decimal, note: str | None, actor_id: int) -> HourLog:
    log = await session.scalar(select(HourLog).where(HourLog.va_id == va_id, HourLog.client_id == client_id, HourLog.work_date == work_date).order_by(HourLog.id.desc()))
    if log:
        log.hours = hours
        if note is not None:
            log.note = note
        log.updated_at = datetime.utcnow()
    else:
        log = HourLog(va_id=va_id, client_id=client_id, work_date=work_date, hours=hours, note=note)
        session.add(log)
    await session.flush()
    await write_audit(session, client_id=client_id, actor_id=actor_id, action='hours_edited', entity_type='hour_log', entity_id=log.id, details={'work_date': work_date.isoformat(), 'hours': str(hours), 'note': note})
    return log


async def logs_for_week(session: AsyncSession, *, va_id: int, client_id: int, week_start: date) -> list[HourLog]:
    week_end = week_start + timedelta(days=6)
    rows = await session.scalars(select(HourLog).where(HourLog.va_id == va_id, HourLog.client_id == client_id, HourLog.work_date >= week_start, HourLog.work_date <= week_end).order_by(HourLog.work_date.asc(), HourLog.id.asc()))
    return list(rows.all())


async def get_or_create_timesheet(session: AsyncSession, *, va_id: int, client_id: int, week_start: date) -> Timesheet:
    timesheet = await session.scalar(select(Timesheet).where(Timesheet.va_id == va_id, Timesheet.client_id == client_id, Timesheet.week_start_date == week_start))
    if timesheet:
        return timesheet
    timesheet = Timesheet(va_id=va_id, client_id=client_id, week_start_date=week_start)
    session.add(timesheet)
    await session.flush()
    return timesheet


async def submit_hours(session: AsyncSession, *, va_id: int, client_id: int, actor_id: int, today: date) -> tuple[Timesheet, list[HourLog]]:
    week_start = week_start_for(today)
    logs = await logs_for_week(session, va_id=va_id, client_id=client_id, week_start=week_start)
    timesheet = await get_or_create_timesheet(session, va_id=va_id, client_id=client_id, week_start=week_start)
    total = sum((Decimal(str(log.hours)) for log in logs), Decimal('0'))
    timesheet.total_hours = total
    timesheet.status = TimesheetStatus.SUBMITTED
    timesheet.submitted_at = datetime.utcnow()
    timesheet.query_note = None
    for log in logs:
        log.timesheet_id = timesheet.id
    await session.flush()
    await write_audit(session, client_id=client_id, actor_id=actor_id, action='timesheet_submitted', entity_type='timesheet', entity_id=timesheet.id, details={'week_start': week_start.isoformat(), 'total_hours': str(total)})
    return timesheet, logs


async def pending_timesheets(session: AsyncSession, *, client_id: int) -> list[Timesheet]:
    rows = await session.scalars(select(Timesheet).where(Timesheet.client_id == client_id, Timesheet.status.in_([TimesheetStatus.SUBMITTED, TimesheetStatus.CLIENT_PENDING, TimesheetStatus.QUERIED])).order_by(Timesheet.week_start_date.desc()))
    return list(rows.all())


async def get_timesheet(session: AsyncSession, *, timesheet_id: int, client_id: int | None = None) -> Timesheet | None:
    stmt = select(Timesheet).where(Timesheet.id == timesheet_id)
    if client_id is not None:
        stmt = stmt.where(Timesheet.client_id == client_id)
    return await session.scalar(stmt)


async def get_user(session: AsyncSession, *, user_id: int, client_id: int | None = None) -> User | None:
    stmt = select(User).where(User.id == user_id)
    if client_id is not None:
        stmt = stmt.where(User.client_id == client_id)
    return await session.scalar(stmt)


async def approve_by_supervisor(session: AsyncSession, *, timesheet: Timesheet, supervisor_id: int) -> Timesheet:
    timesheet.status = TimesheetStatus.CLIENT_PENDING
    timesheet.sup_approved_by = supervisor_id
    timesheet.sup_approved_at = datetime.utcnow()
    await session.flush()
    await write_audit(session, client_id=timesheet.client_id, actor_id=supervisor_id, action='timesheet_supervisor_approved', entity_type='timesheet', entity_id=timesheet.id)
    return timesheet


async def approve_by_client(session: AsyncSession, *, timesheet: Timesheet, client_user_id: int) -> Timesheet:
    timesheet.status = TimesheetStatus.APPROVED
    timesheet.client_approved_by = client_user_id
    timesheet.client_approved_at = datetime.utcnow()
    await session.flush()
    await write_audit(session, client_id=timesheet.client_id, actor_id=client_user_id, action='timesheet_client_approved', entity_type='timesheet', entity_id=timesheet.id)
    return timesheet


async def mark_queried(session: AsyncSession, *, timesheet: Timesheet, actor_id: int, note: str | None = None) -> Timesheet:
    timesheet.status = TimesheetStatus.QUERIED
    if note:
        timesheet.query_note = note
    await session.flush()
    await write_audit(session, client_id=timesheet.client_id, actor_id=actor_id, action='timesheet_queried', entity_type='timesheet', entity_id=timesheet.id, details={'note': note})
    return timesheet


async def approved_hours_in_period(session: AsyncSession, *, va_id: int, client_id: int, period_start: date, period_end: date) -> list[HourLog]:
    rows = await session.scalars(
        select(HourLog)
        .join(Timesheet, HourLog.timesheet_id == Timesheet.id)
        .where(
            HourLog.va_id == va_id,
            HourLog.client_id == client_id,
            HourLog.work_date >= period_start,
            HourLog.work_date <= period_end,
            Timesheet.status == TimesheetStatus.APPROVED,
        )
        .order_by(HourLog.work_date.asc(), HourLog.id.asc())
    )
    return list(rows.all())


async def total_hours_this_week(session: AsyncSession, *, client_id: int, week_start: date) -> Decimal:
    week_end = week_start + timedelta(days=6)
    rows = await session.scalars(select(HourLog.hours).where(HourLog.client_id == client_id, HourLog.work_date >= week_start, HourLog.work_date <= week_end))
    total = Decimal('0')
    for value in rows.all():
        total += Decimal(str(value))
    return total


async def create_or_get_timesheet(session, *, va_id: int, client_id: int, week_start: date):
    return await get_or_create_timesheet(session, va_id=va_id, client_id=client_id, week_start=week_start)
