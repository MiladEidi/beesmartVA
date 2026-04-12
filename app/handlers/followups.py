from telegram import Update
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.enums import Role
from app.services.auth import resolve_actor
from app.services.followups import create_connection, find_connection, mark_booked, mark_followdone, mark_noresponse, mark_replied, pending_followups
from app.services.users import get_user_by_internal_id
from app.utils.formatters import render_connections


async def connection_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text('Use: /connection [name] [platform] (title) (company)')
        return
    name = context.args[0]
    platform = context.args[1]
    title = context.args[2] if len(context.args) > 2 else None
    company = context.args[3] if len(context.args) > 3 else None
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role != Role.VA or actor.role_user_id is None:
            await update.message.reply_text('Only VAs can log connections.')
            return
        item = await create_connection(session, client_id=actor.client_id, va_id=actor.role_user_id, prospect_name=name, platform=platform, title=title, company=company)
        await session.commit()
        await update.message.reply_text(f'Connection logged for {item.prospect_name}. Follow-up scheduled automatically.')


async def followups_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor:
            await update.message.reply_text('This group has not been set up yet.')
            return
        items = await pending_followups(session, client_id=actor.client_id)
        await update.message.reply_text(render_connections(items))


async def followdone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text('Use: /followdone [name]')
        return
    name = context.args[0]
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role != Role.VA or actor.role_user_id is None:
            await update.message.reply_text('Only VAs can use /followdone.')
            return
        item = await find_connection(session, client_id=actor.client_id, name=name)
        if not item:
            await update.message.reply_text('Connection not found.')
            return
        await mark_followdone(session, connection=item, actor_id=actor.role_user_id)
        await session.commit()
        await update.message.reply_text(f'Follow-up logged for {item.prospect_name}.')


async def replied_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text('Use: /replied [name]')
        return
    name = context.args[0]
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role != Role.VA or actor.role_user_id is None:
            await update.message.reply_text('Only VAs can use /replied.')
            return
        item = await find_connection(session, client_id=actor.client_id, name=name)
        if not item:
            await update.message.reply_text('Connection not found.')
            return
        await mark_replied(session, connection=item, actor_id=actor.role_user_id)
        va = await get_user_by_internal_id(session, client_id=actor.client_id, user_id=actor.role_user_id)
        if va and va.supervisor:
            await context.bot.send_message(chat_id=va.supervisor.telegram_user_id, text=f'{item.prospect_name} replied. The client may need to take over.')
        await session.commit()
        await update.message.reply_text(f'Reply logged for {item.prospect_name}.')


async def booked_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text('Use: /booked [name] (date)')
        return
    name = context.args[0]
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role != Role.VA or actor.role_user_id is None:
            await update.message.reply_text('Only VAs can use /booked.')
            return
        item = await find_connection(session, client_id=actor.client_id, name=name)
        if not item:
            await update.message.reply_text('Connection not found.')
            return
        await mark_booked(session, connection=item, actor_id=actor.role_user_id)
        await session.commit()
        await update.message.reply_text(f'Meeting booked for {item.prospect_name}.')


async def noresponse_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text('Use: /noresponse [name]')
        return
    name = context.args[0]
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role != Role.VA or actor.role_user_id is None:
            await update.message.reply_text('Only VAs can use /noresponse.')
            return
        item = await find_connection(session, client_id=actor.client_id, name=name)
        if not item:
            await update.message.reply_text('Connection not found.')
            return
        await mark_noresponse(session, connection=item, actor_id=actor.role_user_id)
        await session.commit()
        await update.message.reply_text(f'Closed {item.prospect_name} as no response.')
