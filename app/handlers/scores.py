from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.enums import Role, ScoreTrigger
from app.services.auth import resolve_actor
from app.services.scores import get_client_user, save_score, score_history
from app.utils.formatters import render_scores
from app.utils.telegram import score_keyboard


async def scores_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role != Role.SUPERVISOR:
            await update.message.reply_text('Only supervisors can use /scores.')
            return
        items = await score_history(session, client_id=actor.client_id)
        await update.message.reply_text(render_scores(items))


async def send_scorecheck_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        client_user = await get_client_user(session, client_id=actor.client_id) if actor else None
        if not actor or actor.role != Role.SUPERVISOR or not client_user:
            await update.message.reply_text('A supervisor and a registered client user are required.')
            return
        target = f'{actor.client_id}:{date.today().strftime("%B-%Y")}:manual'
        await context.bot.send_message(chat_id=client_user.telegram_user_id, text='Quick check-in: how are things going? Tap a score below.', reply_markup=score_keyboard(target))
        await update.message.reply_text('Satisfaction check sent to the client.')
