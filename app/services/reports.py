from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import DraftStatus, Role, TaskStatus, TimesheetStatus
from app.models import Connection, Draft, HourLog, SatisfactionScore, Task, Timesheet, User
from app.services.followups import followup_counts
from app.services.tasks import task_counts


async def weekly_report(session: AsyncSession, *, client_id: int, client_name: str, week_start: date) -> str:
    week_end = week_start + timedelta(days=6)
    open_tasks, flagged_tasks = await task_counts(session, client_id=client_id)
    completed_tasks = len(
        (
            await session.scalars(
                select(Task).where(
                    Task.client_id == client_id,
                    Task.status == TaskStatus.DONE,
                    Task.completed_at >= week_start,
                    Task.completed_at <= week_end + timedelta(days=1),
                )
            )
        ).all()
    )
    open_task_rows = list(
        (
            await session.scalars(
                select(Task)
                .where(Task.client_id == client_id, Task.status.in_([TaskStatus.OPEN, TaskStatus.FLAGGED]))
                .order_by(Task.created_at.asc())
                .limit(5)
            )
        ).all()
    )
    connections = list(
        (
            await session.scalars(
                select(Connection).where(
                    Connection.client_id == client_id,
                    Connection.connected_at >= week_start,
                    Connection.connected_at <= week_end + timedelta(days=1),
                )
            )
        ).all()
    )
    replies = len([c for c in connections if c.status.value in {"REPLIED", "BOOKED"}])
    booked = len([c for c in connections if c.status.value == "BOOKED"])
    drafts_submitted = len(
        (
            await session.scalars(
                select(Draft).where(
                    Draft.client_id == client_id,
                    Draft.submitted_at >= week_start,
                    Draft.submitted_at <= week_end + timedelta(days=1),
                )
            )
        ).all()
    )
    approved = len(
        (
            await session.scalars(
                select(Draft).where(
                    Draft.client_id == client_id,
                    Draft.actioned_at >= week_start,
                    Draft.actioned_at <= week_end + timedelta(days=1),
                    Draft.status == DraftStatus.APPROVED,
                )
            )
        ).all()
    )
    revised = len(
        (
            await session.scalars(
                select(Draft).where(
                    Draft.client_id == client_id,
                    Draft.actioned_at >= week_start,
                    Draft.actioned_at <= week_end + timedelta(days=1),
                    Draft.status == DraftStatus.REVISED,
                )
            )
        ).all()
    )
    hours_rows = (
        await session.scalars(
            select(HourLog.hours).where(HourLog.client_id == client_id, HourLog.work_date >= week_start, HourLog.work_date <= week_end)
        )
    ).all()
    total_hours = sum((Decimal(str(v)) for v in hours_rows), Decimal("0"))
    pending_ts = list(
        (
            await session.scalars(
                select(Timesheet).where(
                    Timesheet.client_id == client_id,
                    Timesheet.status.in_([TimesheetStatus.SUBMITTED, TimesheetStatus.CLIENT_PENDING, TimesheetStatus.QUERIED]),
                )
            )
        ).all()
    )
    lines = [
        "BeeSmartVA — Weekly Check-in",
        f"Week of {week_start.isoformat()} → {week_end.isoformat()} · Client: {client_name}",
        "",
        "Tasks",
        f"  Completed this week: {completed_tasks}",
        f"  Still open: {open_tasks}",
        f"  Flagged: {flagged_tasks}",
        "",
        "Outreach & Follow-ups",
        f"  New connections: {len(connections)}",
        f"  Pending follow-ups: {await followup_counts(session, client_id=client_id)}",
        f"  Replies received: {replies}",
        f"  Meetings booked: {booked}",
        "",
        "Content",
        f"  Drafts submitted: {drafts_submitted}",
        f"  Approved: {approved}",
        f"  Revisions requested: {revised}",
        "",
        "Hours",
        f"  Logged this week: {total_hours}h",
        f"  Pending timesheets: {len(pending_ts)}",
    ]
    if open_task_rows:
        lines.extend(["", "Open tasks:"])
        for task in open_task_rows:
            lines.append(f"  #{task.id} — {task.description}")
    return "\n".join(lines)


async def monthly_report(session: AsyncSession, *, client_id: int, client_name: str, month_label: str) -> str:
    scores = list(
        (
            await session.scalars(
                select(SatisfactionScore)
                .where(SatisfactionScore.client_id == client_id)
                .order_by(SatisfactionScore.responded_at.desc())
                .limit(3)
            )
        ).all()
    )
    tasks_done = len((await session.scalars(select(Task).where(Task.client_id == client_id, Task.status == TaskStatus.DONE))).all())
    drafts = len((await session.scalars(select(Draft).where(Draft.client_id == client_id))).all())
    hours_rows = (await session.scalars(select(HourLog.hours).where(HourLog.client_id == client_id))).all()
    total_hours = sum((Decimal(str(v)) for v in hours_rows), Decimal("0"))
    score_trend = " → ".join(str(x.score) for x in reversed(scores)) if scores else "No scores yet"
    return (
        f"BeeSmartVA — Monthly Report\n"
        f"Client: {client_name} · Period: {month_label}\n\n"
        f"Total completed tasks: {tasks_done}\n"
        f"Total drafts handled: {drafts}\n"
        f"Total logged hours: {total_hours}h\n"
        f"Satisfaction trend: {score_trend}"
    )


async def client_weekly_digest(session: AsyncSession, *, client_id: int, client_name: str, week_start: date) -> str:
    week_end = week_start + timedelta(days=6)
    users = list(
        (
            await session.scalars(
                select(User)
                .where(User.client_id == client_id, User.role == Role.VA, User.active.is_(True))
                .order_by(User.display_name.asc())
            )
        ).all()
    )
    done_tasks = list(
        (
            await session.scalars(
                select(Task)
                .where(
                    Task.client_id == client_id,
                    Task.status == TaskStatus.DONE,
                    Task.completed_at >= week_start,
                    Task.completed_at <= week_end + timedelta(days=1),
                )
                .order_by(Task.completed_at.desc())
            )
        ).all()
    )
    pending_client_ts = list(
        (
            await session.scalars(
                select(Timesheet)
                .where(Timesheet.client_id == client_id, Timesheet.status == TimesheetStatus.CLIENT_PENDING)
                .order_by(Timesheet.week_start_date.asc())
            )
        ).all()
    )
    drafted = list(
        (
            await session.scalars(
                select(Draft)
                .where(
                    Draft.client_id == client_id,
                    Draft.submitted_at >= week_start,
                    Draft.submitted_at <= week_end + timedelta(days=1),
                )
                .order_by(Draft.submitted_at.desc())
                .limit(5)
            )
        ).all()
    )
    booked = len(
        (
            await session.scalars(
                select(Connection).where(
                    Connection.client_id == client_id,
                    Connection.status == "BOOKED",
                    Connection.connected_at >= week_start,
                    Connection.connected_at <= week_end + timedelta(days=1),
                )
            )
        ).all()
    )

    lines = [
        f"Weekly client digest — {client_name}",
        f"Coverage: {week_start.isoformat()} → {week_end.isoformat()}",
        "",
        "What was done this week",
        f"• Tasks completed: {len(done_tasks)}",
        f"• Drafts submitted: {len(drafted)}",
        f"• Meetings booked: {booked}",
    ]
    for va in users:
        hours_rows = (
            await session.scalars(
                select(HourLog.hours).where(
                    HourLog.client_id == client_id,
                    HourLog.va_id == va.id,
                    HourLog.work_date >= week_start,
                    HourLog.work_date <= week_end,
                )
            )
        ).all()
        total_hours = sum((Decimal(str(v)) for v in hours_rows), Decimal("0"))
        if total_hours:
            lines.append(f"• {va.display_name}: {total_hours}h logged")

    if done_tasks:
        lines.extend(["", "Latest completed tasks"])
        for task in done_tasks[:5]:
            lines.append(f"• #{task.id} {task.description}")

    if pending_client_ts:
        lines.extend(["", "Payment / approval items waiting for you"])
        for ts in pending_client_ts:
            va = await session.get(User, ts.va_id)
            lines.append(
                f"• Timesheet #{ts.id} · {va.display_name if va else ts.va_id} · week {ts.week_start_date.isoformat()} · {ts.total_hours}h"
            )
        lines.append("Use the approval buttons already sent by the bot to confirm these timesheets.")
    else:
        lines.extend(["", "No weekly payment confirmations are waiting from you right now."])

    return "\n".join(lines)


async def supervisor_action_digest(session: AsyncSession, *, client_id: int, client_name: str) -> str:
    pending_ts = list(
        (
            await session.scalars(
                select(Timesheet)
                .where(Timesheet.client_id == client_id, Timesheet.status == TimesheetStatus.SUBMITTED)
                .order_by(Timesheet.submitted_at.asc())
            )
        ).all()
    )
    pending_drafts = list(
        (
            await session.scalars(
                select(Draft)
                .where(Draft.client_id == client_id, Draft.status == DraftStatus.PENDING)
                .order_by(Draft.submitted_at.asc())
            )
        ).all()
    )
    flagged_tasks = list(
        (
            await session.scalars(
                select(Task)
                .where(Task.client_id == client_id, Task.status == TaskStatus.FLAGGED)
                .order_by(Task.created_at.asc())
            )
        ).all()
    )
    if not pending_ts and not pending_drafts and not flagged_tasks:
        return ""
    lines = [f"Supervisor action digest — {client_name}"]
    if pending_ts:
        lines.append(f"• Timesheets waiting for review: {len(pending_ts)}")
    if pending_drafts:
        lines.append(f"• Drafts waiting for review: {len(pending_drafts)}")
    if flagged_tasks:
        lines.append(f"• Flagged tasks needing attention: {len(flagged_tasks)}")
    return "\n".join(lines)


async def executive_summary(session: AsyncSession, *, telegram_user_id: int, include_financials: bool = False) -> str:
    memberships = list(
        (
            await session.scalars(
                select(User).where(User.telegram_user_id == telegram_user_id, User.role.in_([Role.SUPERVISOR, Role.BUSINESS_MANAGER]))
            )
        ).all()
    )
    if not memberships:
        return "You are not registered as a supervisor or business manager in any group."
    total_open = total_flagged = total_pending_ts = 0
    total_approved_hours = Decimal("0")
    lines = ["Executive summary"]
    for member in memberships:
        open_tasks, flagged = await task_counts(session, client_id=member.client_id)
        pending_ts = len(
            (
                await session.scalars(
                    select(Timesheet).where(
                        Timesheet.client_id == member.client_id,
                        Timesheet.status.in_([TimesheetStatus.SUBMITTED, TimesheetStatus.CLIENT_PENDING, TimesheetStatus.QUERIED]),
                    )
                )
            ).all()
        )
        total_open += open_tasks
        total_flagged += flagged
        total_pending_ts += pending_ts
        approved_hours_rows = (
            await session.scalars(
                select(Timesheet.total_hours).where(Timesheet.client_id == member.client_id, Timesheet.status == TimesheetStatus.APPROVED)
            )
        ).all()
        approved_hours = sum((Decimal(str(v)) for v in approved_hours_rows), Decimal("0"))
        total_approved_hours += approved_hours
        line = f"Client #{member.client_id}: role={member.role.value} · open={open_tasks} · flagged={flagged} · pending_timesheets={pending_ts}"
        if include_financials:
            last_score = await session.scalar(
                select(SatisfactionScore.score)
                .where(SatisfactionScore.client_id == member.client_id)
                .order_by(SatisfactionScore.responded_at.desc())
                .limit(1)
            )
            line += f" · approved_hours={approved_hours}"
            if last_score is not None:
                line += f" · latest_score={last_score}/5"
        lines.append(line)
    totals = f"Portfolio totals: open={total_open}, flagged={total_flagged}, pending_timesheets={total_pending_ts}"
    if include_financials:
        totals += f", approved_hours={total_approved_hours}"
    lines.extend(["", totals])
    return "\n".join(lines)


async def supervisor_cross_group_summary(session: AsyncSession, *, supervisor_tg_id: int) -> str:
    return await executive_summary(session, telegram_user_id=supervisor_tg_id, include_financials=False)
