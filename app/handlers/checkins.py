from telegram import Update
from telegram.ext import ContextTypes

from sqlalchemy import select

from app.db import SessionLocal
from app.enums import Role
from app.services.auth import resolve_actor
from app.services.followups import followup_counts
from app.services.hours import pending_timesheets, total_hours_this_week
from app.services.tasks import task_counts
from app.services.users import get_user_by_internal_id
from app.utils.dates import week_start_for
from app.utils.formatters import render_stats


async def _notify_supervisor(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str, message: str) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role != Role.VA or actor.role_user_id is None:
            await update.message.reply_text('Only VAs can use this command.')
            return
        va = await get_user_by_internal_id(session, client_id=actor.client_id, user_id=actor.role_user_id)
        if not va or not va.supervisor:
            await update.message.reply_text(
                'No supervisor is assigned to your account yet.\n\n'
                'Ask your Manager to run:\n'
                f'  /set supervisor [your_user_id] [supervisor_user_id]\n\n'
                'Your user ID is shown when you run /start in the group.'
            )
            return
        text = f'{prefix}\n\nFrom: {va.display_name}\nGroup: {update.effective_chat.title or update.effective_chat.id}\n\n{message}'
        try:
            await context.bot.send_message(chat_id=va.supervisor.telegram_user_id, text=text)
            await update.message.reply_text('✅ Message sent to your supervisor.')
        except Exception:
            await update.message.reply_text(
                '⚠️ Could not reach your supervisor.\n\n'
                'They may not have started a private chat with this bot yet.\n'
                f'Ask {va.supervisor.display_name} to open a private chat with this bot and send /start.'
            )


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = ' '.join(context.args).strip()
    if not message:
        await update.message.reply_text('Use: /ask [message]')
        return
    await _notify_supervisor(update, context, 'Your VA has a quick question:', message)


async def flag_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = ' '.join(context.args).strip()
    if not message:
        await update.message.reply_text('Use: /flag [note]')
        return
    await _notify_supervisor(update, context, 'Private heads-up from your VA:', message)


async def confirm_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = ' '.join(context.args).strip()
    if not message:
        await update.message.reply_text('Use: /confirm [question]')
        return
    await _notify_supervisor(update, context, 'Quick yes/no confirmation requested:', message)


async def notify_client_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = ' '.join(context.args).strip()
    if not message:
        await update.message.reply_text('Use: /notify client [message]')
        return
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role != Role.VA:
            await update.message.reply_text('Only VAs can notify the client.')
            return
        from app.models import User
        client_user = await session.scalar(select(User).where(User.client_id == actor.client_id, User.role == Role.CLIENT))
        if client_user:
            try:
                await context.bot.send_message(chat_id=client_user.telegram_user_id, text=message)
                await update.message.reply_text('✅ Message sent to the client.')
            except Exception:
                await update.message.reply_text(
                    '⚠️ Could not reach the client.\n\n'
                    'They may not have started a private chat with this bot yet.\n'
                    f'Ask {client_user.display_name} to open a private chat with this bot and send /start.'
                )
        else:
            await update.message.reply_text(
                'No client user is registered in this group yet.\n\n'
                'Ask your Manager to add one with:\n'
                '  /adduser [telegram_id] CLIENT [Name]'
            )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from datetime import date

    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor:
            await update.message.reply_text('This group has not been set up yet.')
            return
        open_count, flagged_count = await task_counts(session, client_id=actor.client_id)
        hours = await total_hours_this_week(session, client_id=actor.client_id, week_start=week_start_for(date.today()))
        pending = await pending_timesheets(session, client_id=actor.client_id)
        followups = await followup_counts(session, client_id=actor.client_id)
        await update.message.reply_text(render_stats(open_count, flagged_count, hours, len(pending), pending_followups=followups))
