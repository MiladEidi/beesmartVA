from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from telegram import Bot

from app.db import SessionLocal
from app.enums import Role, TimesheetStatus
from app.models import Client, User, Timesheet
from app.services.drafts import overdue_pending_drafts
from app.services.followups import due_followups
from app.services.hours import pending_timesheets
from app.services.reports import (
    client_weekly_digest,
    executive_summary,
    monthly_report,
    supervisor_action_digest,
    weekly_report,
)
from app.utils.dates import week_start_for

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def _users_for_roles(session, client_id: int, roles: list[Role]) -> list[User]:
    return list((await session.scalars(select(User).where(User.client_id == client_id, User.role.in_(roles), User.active.is_(True)))).all())


async def job_daily(bot: Bot) -> None:
    async with SessionLocal() as session:
        clients = list((await session.scalars(select(Client))).all())
        now = datetime.utcnow()
        for client in clients:
            local = now.astimezone(ZoneInfo(client.timezone))
            week_start = week_start_for(local.date())

            # VA nudges.
            if local.hour == 9:
                vas = await _users_for_roles(session, client.id, [Role.VA])
                for va in vas:
                    await bot.send_message(chat_id=va.telegram_user_id, text='Good morning. Please check your open tasks, due follow-ups, and any pending updates in BeeSmartVA.')
            if local.weekday() == 4 and local.hour == 16:
                vas = await _users_for_roles(session, client.id, [Role.VA])
                for va in vas:
                    await bot.send_message(chat_id=va.telegram_user_id, text='Weekly reminder: review your work log with /myweek and submit your timesheet if the week is ready.')

            # Mid-day nudge for VAs to log hours today.
            if local.hour == 12:
                vas = await _users_for_roles(session, client.id, [Role.VA])
                for va in vas:
                    await bot.send_message(chat_id=va.telegram_user_id, text='Quick reminder: have you logged your work hours for today? Use /hours today [hours] to keep things on track.')

            # Supervisor + business manager operational visibility.
            if local.weekday() in {0, 1, 2, 3, 4} and local.hour == 14:
                digest = await supervisor_action_digest(session, client_id=client.id, client_name=client.name)
                if digest:
                    recipients = await _users_for_roles(session, client.id, [Role.SUPERVISOR, Role.BUSINESS_MANAGER])
                    sent = set()
                    for user in recipients:
                        if user.telegram_user_id in sent:
                            continue
                        sent.add(user.telegram_user_id)
                        await bot.send_message(chat_id=user.telegram_user_id, text=digest)

            # Weekly ops summary for internal team.
            if local.weekday() == 0 and local.hour == 10:
                report = await weekly_report(session, client_id=client.id, client_name=client.name, week_start=week_start)
                recipients = await _users_for_roles(session, client.id, [Role.SUPERVISOR, Role.BUSINESS_MANAGER])
                for user in recipients:
                    await bot.send_message(chat_id=user.telegram_user_id, text=report)

            # Monthly report only to internal managers, not clients.
            if local.weekday() == 0 and local.day <= 7 and local.hour == 11:
                report = await monthly_report(session, client_id=client.id, client_name=client.name, month_label=local.strftime('%B %Y'))
                recipients = await _users_for_roles(session, client.id, [Role.SUPERVISOR, Role.BUSINESS_MANAGER])
                for user in recipients:
                    await bot.send_message(chat_id=user.telegram_user_id, text=report)

            # Supervisor reminder: timesheets awaiting their review.
            if local.weekday() == 1 and local.hour == 10:
                sup_timesheets = list(
                    (await session.scalars(
                        select(Timesheet).where(
                            Timesheet.client_id == client.id,
                            Timesheet.status == TimesheetStatus.SUBMITTED
                        )
                    )).all()
                )
                if sup_timesheets:
                    recipients = await _users_for_roles(session, client.id, [Role.SUPERVISOR, Role.BUSINESS_MANAGER])
                    pending_count = len(sup_timesheets)
                    for user in recipients:
                        await bot.send_message(
                            chat_id=user.telegram_user_id,
                            text=f'📋 Reminder: You have {pending_count} timesheet(s) pending your review. Use /timesheets to see them.'
                        )

            # Client reminder: timesheets awaiting their final approval.
            if local.weekday() == 4 and local.hour == 9:
                client_timesheets = list(
                    (await session.scalars(
                        select(Timesheet).where(
                            Timesheet.client_id == client.id,
                            Timesheet.status == TimesheetStatus.CLIENT_PENDING
                        )
                    )).all()
                )
                if client_timesheets:
                    clients_users = await _users_for_roles(session, client.id, [Role.CLIENT])
                    pending_count = len(client_timesheets)
                    for user in clients_users:
                        await bot.send_message(
                            chat_id=user.telegram_user_id,
                            text=f'✅ Reminder: {pending_count} timesheet(s) waiting for your final approval. Check your messages for approval buttons.'
                        )

            # Client digest only once every two weeks to reduce noise.
            if local.weekday() == 4 and local.hour == 17 and local.isocalendar()[1] % 2 == 0:
                clients_users = await _users_for_roles(session, client.id, [Role.CLIENT])
                if clients_users:
                    digest = await client_weekly_digest(session, client_id=client.id, client_name=client.name, week_start=week_start)
                    for user in clients_users:
                        await bot.send_message(chat_id=user.telegram_user_id, text=digest)

        # Follow-up reminders stay VA-only.
        for item in await due_followups(session):
            va = await session.scalar(select(User).where(User.id == item.va_id))
            if va and va.active:
                await bot.send_message(chat_id=va.telegram_user_id, text=f'Time to follow up with {item.prospect_name} on {item.platform}.')

        # Draft reminders go to supervisors / business managers only, not clients.
        for draft in await overdue_pending_drafts(session):
            recipients = await _users_for_roles(session, draft.client_id, [Role.SUPERVISOR, Role.BUSINESS_MANAGER])
            for user in recipients:
                await bot.send_message(chat_id=user.telegram_user_id, text=f'Heads-up: draft {draft.draft_code} is still pending review.')


async def job_management_summary(bot: Bot) -> None:
    async with SessionLocal() as session:
        managers = list((await session.scalars(select(User).where(User.role.in_([Role.SUPERVISOR, Role.BUSINESS_MANAGER]), User.active.is_(True)))).all())
        seen = set()
        for manager in managers:
            if manager.telegram_user_id in seen:
                continue
            seen.add(manager.telegram_user_id)
            include_financials = manager.role == Role.BUSINESS_MANAGER
            summary = await executive_summary(session, telegram_user_id=manager.telegram_user_id, include_financials=include_financials)
            await bot.send_message(chat_id=manager.telegram_user_id, text=summary)


def configure_scheduler(bot: Bot) -> None:
    if scheduler.running:
        return
    scheduler.add_job(job_daily, 'cron', minute='*/30', kwargs={'bot': bot}, id='daily-scan', replace_existing=True)
    scheduler.add_job(job_management_summary, 'cron', day_of_week='mon', hour=12, minute=0, kwargs={'bot': bot}, id='management-summary', replace_existing=True)
    scheduler.start()
