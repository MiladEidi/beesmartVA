from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.enums import Role
from app.models import User
from app.services.auth import resolve_actor
from app.services.hours import edit_hours, get_user, log_hours, logs_for_week, pending_timesheets, submit_hours
from app.services.invoices import invoice_summary, mark_invoiced
from app.services.permissions import has_manager_access
from app.services.users import decrypt_hourly_rate, get_user_by_display_id
from app.utils.dates import current_week_range, parse_date_maybe
from app.utils.formatters import render_myweek, render_timesheet_table
from app.utils.telegram import timesheet_supervisor_keyboard


async def hours_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text('Use: /hours [date|today|yesterday] [hours] (note) or /hours edit ...')
        return
    if context.args[0].lower() == 'edit':
        await _hours_edit(update, context)
        return
    if len(context.args) < 2:
        await update.message.reply_text('Use: /hours [date|today|yesterday] [hours] (note)')
        return
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor:
            await update.message.reply_text(
                'Hours must be logged in your team group, not in a private chat.\n\n'
                'Switch to your team\'s Telegram group and run the command there.\n\n'
                'If this IS the team group and you see this error, the workspace has\n'
                'not been set up yet. Ask your Manager to run /setup.'
            )
            return
        if actor.role_user_id is None:
            await update.message.reply_text(
                'You are not registered in this group yet.\n\n'
                'Ask your Manager to add you:\n'
                '  /adduser [your_telegram_id] VA [Your Name]\n\n'
                'Your Telegram ID: message @userinfobot to get it.'
            )
            return
        if actor.role != Role.VA:
            await update.message.reply_text(
                f'Only VAs can log hours. Your role is {actor.role.value}.\n\n'
                'If you believe this is incorrect, contact your Manager.'
            )
            return
        user = await get_user(session, user_id=actor.role_user_id, client_id=actor.client_id)
        work_date = parse_date_maybe(context.args[0], user.timezone)
        try:
            hours = Decimal(context.args[1])
        except Exception:
            await update.message.reply_text('Hours must be a number, e.g. 4 or 2.5')
            return
        if hours <= 0:
            await update.message.reply_text('Hours must be greater than zero.')
            return
        if hours > 24:
            await update.message.reply_text('Hours cannot exceed 24 in a single entry.')
            return
        note = ' '.join(context.args[2:]).strip() or None
        await log_hours(session, va_id=actor.role_user_id, client_id=actor.client_id, work_date=work_date, hours=hours, note=note)
        await session.commit()
        await update.message.reply_text(f'✅ Logged {hours}h for {work_date.isoformat()}.')


async def _hours_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role_user_id is None:
            await update.message.reply_text('You are not registered in this group.')
            return
        if actor.role == Role.VA:
            if len(context.args) < 3:
                await update.message.reply_text('Use: /hours edit [date] [hours] (note)')
                return
            user = await get_user(session, user_id=actor.role_user_id, client_id=actor.client_id)
            work_date = parse_date_maybe(context.args[1], user.timezone)
            try:
                hours = Decimal(context.args[2])
            except Exception:
                await update.message.reply_text('Hours must be a number, e.g. 4 or 2.5')
                return
            if hours <= 0:
                await update.message.reply_text('Hours must be greater than zero.')
                return
            note = ' '.join(context.args[3:]).strip() or None
            await edit_hours(session, va_id=actor.role_user_id, client_id=actor.client_id, work_date=work_date, hours=hours, note=note, actor_id=actor.role_user_id)
            await session.commit()
            await update.message.reply_text('✅ Hour entry updated.')
            return
        if has_manager_access(actor.role):
            if len(context.args) < 4:
                await update.message.reply_text('Use: /hours edit [va_tg_id] [date] [hours] (note)')
                return
            va_tg_id = int(context.args[1])
            va = await session.scalar(select(User).where(User.client_id == actor.client_id, User.telegram_user_id == va_tg_id, User.role == Role.VA))
            if not va:
                await update.message.reply_text('VA not found.')
                return
            work_date = parse_date_maybe(context.args[2], va.timezone)
            try:
                hours = Decimal(context.args[3])
            except Exception:
                await update.message.reply_text('Hours must be a number, e.g. 4 or 2.5')
                return
            if hours <= 0:
                await update.message.reply_text('Hours must be greater than zero.')
                return
            note = ' '.join(context.args[4:]).strip() or None
            await edit_hours(session, va_id=va.id, client_id=actor.client_id, work_date=work_date, hours=hours, note=note, actor_id=actor.role_user_id)
            await session.commit()
            await context.bot.send_message(chat_id=va.telegram_user_id, text=f'Your manager adjusted your hours for {work_date.isoformat()}.')
            await update.message.reply_text('Hour entry updated.')
            return
        await update.message.reply_text('Only VAs and managers can edit hour entries.')


async def myweek_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role != Role.VA or actor.role_user_id is None:
            await update.message.reply_text('⛔ Only VAs can use /myweek.')
            return
        user = await get_user(session, user_id=actor.role_user_id, client_id=actor.client_id)
        week_start, _ = current_week_range(user.timezone)
        logs = await logs_for_week(session, va_id=actor.role_user_id, client_id=actor.client_id, week_start=week_start)
        await update.message.reply_text(render_myweek(logs))


async def submit_hours_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role != Role.VA or actor.role_user_id is None:
            await update.message.reply_text('⛔ Only VAs can submit timesheets.')
            return
        user = await get_user(session, user_id=actor.role_user_id, client_id=actor.client_id)
        timesheet, logs = await submit_hours(session, va_id=actor.role_user_id, client_id=actor.client_id, actor_id=actor.role_user_id, today=date.today())
        if not user.supervisor:
            await session.rollback()
            await update.message.reply_text(
                '⚠️ Cannot submit — no supervisor assigned\n\n'
                'A supervisor must be assigned to your account before you can\n'
                'submit a timesheet. Your hours are saved and will not be lost.\n\n'
                'Ask your Manager to run this command in the group:\n'
                f'  /set supervisor {user.display_id or actor.role_user_id} [supervisor_user_id]  (IDs from /groups)\n\n'
                f'Your user ID: {user.display_id or actor.role_user_id}\n'
                'Share this number with your manager.\n\n'
                'To see all registered users and their IDs: /groups'
            )
            return

        # Read all ORM values BEFORE commit — committing expires the instances,
        # and accessing attributes on expired objects in an async session raises
        # MissingGreenlet, causing the handler to crash silently.
        va_name = user.display_name
        supervisor_tg_id = user.supervisor.telegram_user_id
        supervisor_name = user.supervisor.display_name
        timesheet_id = timesheet.id
        week_start = timesheet.week_start_date
        rate = decrypt_hourly_rate(user)

        await session.commit()
        text = render_timesheet_table(va_name, week_start, logs, rate)

        # Always confirm to the VA first so they always get a response.
        await update.message.reply_text(
            '📤 Timesheet submitted!\n\n'
            'Your supervisor has been notified and will review it shortly.'
        )

        # Notify the supervisor privately. This can fail if the supervisor has
        # never started the bot in private chat — catch that gracefully.
        try:
            await context.bot.send_message(
                chat_id=supervisor_tg_id,
                text='📋 A timesheet is ready for your review.\n\n' + text,
                reply_markup=timesheet_supervisor_keyboard(timesheet_id),
            )
        except Exception:
            # Supervisor notification failed — warn the VA so they can follow up manually.
            await update.message.reply_text(
                '⚠️ Could not notify your supervisor automatically.\n\n'
                'This usually means they have not started the bot in private chat yet.\n\n'
                f'Ask {supervisor_name} to open a private chat with this bot '
                'and send /start — then resubmit your timesheet.'
            )


async def timesheets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or not has_manager_access(actor.role):
            await update.message.reply_text('Only supervisors or managers can use /timesheets.')
            return
        items = await pending_timesheets(session, client_id=actor.client_id)
        if not items:
            await update.message.reply_text('No pending timesheets.')
            return
        lines = [f'#{ts.id} · week={ts.week_start_date.isoformat()} · status={ts.status.value} · total={ts.total_hours}h' for ts in items]
        await update.message.reply_text('\n'.join(lines))


async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role_user_id is None:
            await update.message.reply_text('You are not registered in this group.')
            return
        # VAs can only see their own rate.
        if actor.role == Role.VA:
            user = await get_user(session, user_id=actor.role_user_id, client_id=actor.client_id)
            rate = decrypt_hourly_rate(user)
            if rate:
                await update.message.reply_text(f'💰 Your hourly rate: ${rate}/hr')
            else:
                await update.message.reply_text(
                    '💰 Your hourly rate has not been set yet.\n\n'
                    'Ask your Manager to run:\n'
                    f'  /set rate {user.display_id or actor.role_user_id} [amount]'
                )
            return
        if not has_manager_access(actor.role):
            await update.message.reply_text('Rate information is only available to VAs (own rate), supervisors, and managers.')
            return
        # Managers: show rate for a specific VA by internal user ID arg.
        if context.args:
            try:
                va_display_id = int(context.args[0])
            except ValueError:
                await update.message.reply_text('Use: /rate [va_user_id]')
                return
            va = await get_user_by_display_id(session, client_id=actor.client_id, display_id=va_display_id)
            if va and va.role != Role.VA:
                va = None
            if not va:
                await update.message.reply_text('VA not found.')
                return
            rate = decrypt_hourly_rate(va)
            await update.message.reply_text(f'💰 Rate for {va.display_name}: ${rate or 0}/hr')
        else:
            await update.message.reply_text('Use: /rate [va_user_id] — or use /menu → Set Rate to update a VA\'s rate.')


async def invoice_summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text('Use: /invoice summary [va_tg_id] [YYYY-MM-DD:YYYY-MM-DD]')
        return
    va_tg_id = int(context.args[0])
    start_s, end_s = context.args[1].split(':', 1)
    period_start = date.fromisoformat(start_s); period_end = date.fromisoformat(end_s)
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or not has_manager_access(actor.role):
            await update.message.reply_text('Only supervisors or managers can use invoice commands.')
            return
        va = await session.scalar(select(User).where(User.client_id == actor.client_id, User.telegram_user_id == va_tg_id, User.role == Role.VA))
        if not va:
            await update.message.reply_text('VA not found.')
            return
        text, _, _, _ = await invoice_summary(session, va=va, period_start=period_start, period_end=period_end)
        await update.message.reply_text(text)


async def invoice_sent_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text('Use: /invoice sent [va_tg_id] [YYYY-MM-DD:YYYY-MM-DD]')
        return
    va_tg_id = int(context.args[0])
    start_s, end_s = context.args[1].split(':', 1)
    period_start = date.fromisoformat(start_s); period_end = date.fromisoformat(end_s)
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or not has_manager_access(actor.role) or actor.role_user_id is None:
            await update.message.reply_text('Only supervisors or managers can use invoice commands.')
            return
        va = await session.scalar(select(User).where(User.client_id == actor.client_id, User.telegram_user_id == va_tg_id, User.role == Role.VA))
        if not va:
            await update.message.reply_text('VA not found.')
            return
        period = await mark_invoiced(session, va=va, period_start=period_start, period_end=period_end, actor_id=actor.role_user_id)
        await session.commit()
        await update.message.reply_text(f'Invoice period #{period.id} marked as invoiced.')
