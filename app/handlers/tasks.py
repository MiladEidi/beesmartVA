from telegram import Update
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.enums import FlagReason, Role
from app.services.auth import resolve_actor
from app.services.permissions import has_manager_access
from app.services.tasks import assign_task, complete_task, create_task, flag_task, flagged_tasks, list_open_tasks, overdue_tasks, user_map
from app.services.users import get_user_by_display_id
from app.utils.formatters import render_task_list


async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    description = ' '.join(context.args).strip()
    if not description:
        await update.message.reply_text('Use: /task [description]')
        return
    assignee_id = None
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role_user_id is None:
            await update.message.reply_text('You are not registered in this group.')
            return
        task = await create_task(session, client_id=actor.client_id, created_by=actor.role_user_id, description=description, assigned_to=assignee_id)
        await session.commit()
        await update.message.reply_text(f'Task #{task.id} created.')


async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor:
            await update.message.reply_text('This group has not been set up yet.')
            return
        tasks = await list_open_tasks(session, client_id=actor.client_id)
        await update.message.reply_text(render_task_list(tasks, await user_map(session, client_id=actor.client_id)))


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text('Use: /done [task#]')
        return
    task_id = int(context.args[0])
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role_user_id is None:
            await update.message.reply_text('You are not registered in this group.')
            return
        task = await complete_task(session, client_id=actor.client_id, task_id=task_id, actor_id=actor.role_user_id)
        if not task:
            await update.message.reply_text('Task not found.')
            return
        await session.commit()
        await update.message.reply_text(f'Task #{task.id} completed.')


async def cantdo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text('Use: /cantdo [task#] skill|time (note)')
        return
    try:
        task_id = int(context.args[0]); reason = FlagReason(context.args[1].lower())
    except Exception:
        await update.message.reply_text('Use: /cantdo [task#] skill|time (note)')
        return
    note = ' '.join(context.args[2:]).strip() or None
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role != Role.VA or actor.role_user_id is None:
            await update.message.reply_text('Only VAs can use /cantdo.')
            return
        task = await flag_task(session, client_id=actor.client_id, task_id=task_id, actor_id=actor.role_user_id, reason=reason, note=note)
        if not task:
            await update.message.reply_text('Task not found.')
            return
        await session.commit()
        await update.message.reply_text(f'Task #{task.id} flagged as {reason.value}.')


async def assign_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2 or not context.args[0].isdigit() or not context.args[1].isdigit():
        await update.message.reply_text('Use: /assign [task#] [va_user_id]')
        return
    task_id = int(context.args[0]); va_display_id = int(context.args[1])
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or not has_manager_access(actor.role) or actor.role_user_id is None:
            await update.message.reply_text('Only supervisors or business managers can assign tasks.')
            return
        user = await get_user_by_display_id(session, client_id=actor.client_id, display_id=va_display_id)
        if not user:
            await update.message.reply_text('User not found.')
            return
        task = await assign_task(session, client_id=actor.client_id, task_id=task_id, actor_id=actor.role_user_id, assigned_to=user.id)
        if not task:
            await update.message.reply_text('Task not found.')
            return
        await session.commit()
        await update.message.reply_text(f'Task #{task.id} assigned to {user.display_name}.')


async def overdue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or not has_manager_access(actor.role):
            await update.message.reply_text('Only supervisors or business managers can use /overdue.')
            return
        tasks = await overdue_tasks(session, client_id=actor.client_id)
        await update.message.reply_text(render_task_list(tasks, await user_map(session, client_id=actor.client_id)))


async def flagged_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or not has_manager_access(actor.role):
            await update.message.reply_text('Only supervisors or business managers can use /flagged.')
            return
        tasks = await flagged_tasks(session, client_id=actor.client_id)
        await update.message.reply_text(render_task_list(tasks, await user_map(session, client_id=actor.client_id)))
