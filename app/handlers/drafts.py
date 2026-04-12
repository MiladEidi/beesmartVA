from telegram import Update
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.enums import Role
from app.services.auth import resolve_actor
from app.services.drafts import get_draft_by_code, list_drafts, mark_posted, submit_draft
from app.services.users import get_user_by_internal_id
from app.utils.formatters import render_drafts
from app.utils.telegram import draft_keyboard


async def draft_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text('Use: /draft [platform] [content]')
        return
    platform = context.args[0]
    content = ' '.join(context.args[1:]).strip()
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role != Role.VA or actor.role_user_id is None:
            await update.message.reply_text('Only VAs can submit drafts.')
            return
        draft = await submit_draft(session, client_id=actor.client_id, va_id=actor.role_user_id, platform=platform, content=content)
        await session.commit()
        await update.message.reply_text(f'Draft {draft.draft_code} submitted.')
        # Send draft privately to supervisor for review
        va = await get_user_by_internal_id(session, client_id=actor.client_id, user_id=actor.role_user_id)
        if va and va.supervisor:
            await context.bot.send_message(
                chat_id=va.supervisor.telegram_user_id,
                text=f'Draft {draft.draft_code} for review\nPlatform: {platform}\n\n{content}',
                reply_markup=draft_keyboard(draft.id),
            )


async def drafts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor:
            await update.message.reply_text('This group has not been set up yet.')
            return
        items = await list_drafts(session, client_id=actor.client_id)
        await update.message.reply_text(render_drafts(items))


async def posted_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text('Use: /posted [draft_code]')
        return
    code = context.args[0]
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role != Role.VA or actor.role_user_id is None:
            await update.message.reply_text('Only VAs can mark drafts as posted.')
            return
        draft = await get_draft_by_code(session, client_id=actor.client_id, code=code)
        if not draft:
            await update.message.reply_text('Draft not found.')
            return
        await mark_posted(session, draft=draft, actor_id=actor.role_user_id)
        await session.commit()
        await update.message.reply_text(f'{draft.draft_code} marked as posted.')
