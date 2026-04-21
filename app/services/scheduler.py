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
from app.services.drafts import client_pending_drafts_overdue, overdue_pending_drafts
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


async def _safe_send(bot: Bot, chat_id: int, text: str) -> None:
    """Send a message and swallow delivery errors (user blocked bot, never started it, etc.)."""
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception as exc:
        logger.warning('Scheduled message not delivered to %s: %s', chat_id, exc)


async def job_daily(bot: Bot) -> None:
    try:
        await _job_daily_inner(bot)
    except Exception as exc:
        logger.error('job_daily failed: %s', exc, exc_info=True)


async def _job_daily_inner(bot: Bot) -> None:
    async with SessionLocal() as session:
        clients = list((await session.scalars(select(Client))).all())
        now = datetime.utcnow()
        for client in clients:
            try:
                local = now.astimezone(ZoneInfo(client.timezone))
            except Exception:
                logger.warning('Invalid timezone for client %s: %s', client.id, client.timezone)
                continue
            week_start = week_start_for(local.date())

            # VA nudges.
            if local.hour == 9:
                vas = await _users_for_roles(session, client.id, [Role.VA])
                for va in vas:
                    await _safe_send(bot, va.telegram_user_id, 'Good morning! Check your open tasks, due follow-ups, and any pending updates in BeeSmartVA.')
            if local.weekday() == 4 and local.hour == 16:
                vas = await _users_for_roles(session, client.id, [Role.VA])
                for va in vas:
                    await _safe_send(bot, va.telegram_user_id, 'Weekly reminder: review your work log with /myweek and submit your timesheet if the week is ready.')

            # Mid-day nudge for VAs to log hours today.
            if local.hour == 12:
                vas = await _users_for_roles(session, client.id, [Role.VA])
                for va in vas:
                    await _safe_send(bot, va.telegram_user_id, 'Quick reminder: have you logged your work hours for today? Use /hours today [hours] to keep things on track.')

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
                        await _safe_send(bot, user.telegram_user_id, digest)

            # Weekly ops summary for internal team.
            if local.weekday() == 0 and local.hour == 10:
                report = await weekly_report(session, client_id=client.id, client_name=client.name, week_start=week_start)
                recipients = await _users_for_roles(session, client.id, [Role.SUPERVISOR, Role.BUSINESS_MANAGER])
                for user in recipients:
                    await _safe_send(bot, user.telegram_user_id, report)

            # Monthly report only to internal managers, not clients.
            if local.weekday() == 0 and local.day <= 7 and local.hour == 11:
                report = await monthly_report(session, client_id=client.id, client_name=client.name, month_label=local.strftime('%B %Y'))
                recipients = await _users_for_roles(session, client.id, [Role.SUPERVISOR, Role.BUSINESS_MANAGER])
                for user in recipients:
                    await _safe_send(bot, user.telegram_user_id, report)

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
                        await _safe_send(bot, user.telegram_user_id, f'📋 Reminder: You have {pending_count} timesheet(s) pending your review. Use /timesheets to see them.')

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
                        await _safe_send(bot, user.telegram_user_id, f'✅ Reminder: {pending_count} timesheet(s) are waiting for your final approval. Check your messages for the approval buttons.')

            # Client digest only once every two weeks to reduce noise.
            if local.weekday() == 4 and local.hour == 17 and local.isocalendar()[1] % 2 == 0:
                clients_users = await _users_for_roles(session, client.id, [Role.CLIENT])
                if clients_users:
                    digest = await client_weekly_digest(session, client_id=client.id, client_name=client.name, week_start=week_start)
                    for user in clients_users:
                        await _safe_send(bot, user.telegram_user_id, digest)

        # Follow-up reminders stay VA-only.
        for item in await due_followups(session):
            va = await session.scalar(select(User).where(User.id == item.va_id))
            if va and va.active:
                await _safe_send(bot, va.telegram_user_id, f'Time to follow up with {item.prospect_name} on {item.platform}.')

        # Draft reminders — supervisors for PENDING drafts they haven't reviewed.
        for draft in await overdue_pending_drafts(session):
            recipients = await _users_for_roles(session, draft.client_id, [Role.SUPERVISOR, Role.BUSINESS_MANAGER])
            for user in recipients:
                await _safe_send(bot, user.telegram_user_id, (
                    f'📝 Reminder: draft {draft.draft_code} ({draft.platform}) has been waiting for your review for over 48 hours.\n\n'
                    f'The VA is waiting for feedback before this content can be published.\n\n'
                    f'Use /drafts to see the full queue.'
                ))

        # Draft reminders — clients for CLIENT_PENDING drafts (48h nudge).
        for draft in await client_pending_drafts_overdue(session, hours=48):
            client_users = await _users_for_roles(session, draft.client_id, [Role.CLIENT])
            bm_users = await _users_for_roles(session, draft.client_id, [Role.BUSINESS_MANAGER])
            notified = set()
            for user in client_users + bm_users:
                if user.telegram_user_id in notified:
                    continue
                notified.add(user.telegram_user_id)
                await _safe_send(bot, user.telegram_user_id, (
                    f'📝 Reminder: draft {draft.draft_code} ({draft.platform}) is waiting for your approval.\n\n'
                    f'Your team has prepared content that is ready to post — it just needs your final sign-off.\n\n'
                    f'Check your earlier messages from this bot for the Approve / Request Revision buttons.'
                ))

        # Draft escalation — supervisors alerted when client hasn't reviewed after 72h.
        for draft in await client_pending_drafts_overdue(session, hours=72):
            recipients = await _users_for_roles(session, draft.client_id, [Role.SUPERVISOR, Role.BUSINESS_MANAGER])
            for user in recipients:
                await _safe_send(bot, user.telegram_user_id, (
                    f'⚠️ Escalation: draft {draft.draft_code} ({draft.platform}) has been waiting for client approval for over 72 hours.\n\n'
                    f'You may want to follow up with the client directly.\n\n'
                    f'Use /drafts to view the full queue.'
                ))


async def job_management_summary(bot: Bot) -> None:
    try:
        async with SessionLocal() as session:
            managers = list((await session.scalars(select(User).where(User.role.in_([Role.SUPERVISOR, Role.BUSINESS_MANAGER]), User.active.is_(True)))).all())
            seen = set()
            for manager in managers:
                if manager.telegram_user_id in seen:
                    continue
                seen.add(manager.telegram_user_id)
                include_financials = manager.role == Role.BUSINESS_MANAGER
                summary = await executive_summary(session, telegram_user_id=manager.telegram_user_id, include_financials=include_financials)
                await _safe_send(bot, manager.telegram_user_id, summary)
    except Exception as exc:
        logger.error('job_management_summary failed: %s', exc, exc_info=True)


def configure_scheduler(bot: Bot) -> None:
    if scheduler.running:
        return
    scheduler.add_job(job_daily, 'cron', minute='*/30', kwargs={'bot': bot}, id='daily-scan', replace_existing=True)
    scheduler.add_job(job_management_summary, 'cron', day_of_week='mon', hour=12, minute=0, kwargs={'bot': bot}, id='management-summary', replace_existing=True)
    scheduler.start()
