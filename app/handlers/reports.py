from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.enums import Role
from app.services.auth import resolve_actor
from app.services.permissions import has_manager_access
from app.services.reports import executive_summary, monthly_report, weekly_report
from app.services.users import get_client_by_chat_id
from app.utils.dates import week_start_for


async def weekly_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        client = await get_client_by_chat_id(session, update.effective_chat.id)
        if not actor or not client:
            await update.message.reply_text('This group has not been set up yet.')
            return
        report = await weekly_report(session, client_id=client.id, client_name=client.name, week_start=week_start_for(date.today()))
        await update.message.reply_text(report)


async def monthly_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        client = await get_client_by_chat_id(session, update.effective_chat.id)
        if not actor or not client:
            await update.message.reply_text('This group has not been set up yet.')
            return
        report = await monthly_report(session, client_id=client.id, client_name=client.name, month_label=date.today().strftime('%B %Y'))
        await update.message.reply_text(report)


async def report_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or not has_manager_access(actor.role) or not update.effective_user:
            await update.message.reply_text('Only supervisors and business managers can use /report all.')
            return
        text = await executive_summary(session, telegram_user_id=update.effective_user.id, include_financials=(actor.role == Role.BUSINESS_MANAGER))
        await context.bot.send_message(chat_id=update.effective_user.id, text=text)
        await update.message.reply_text('Executive summary sent to your private chat.')
