from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.enums import Role, ScoreTrigger, TimesheetStatus
from app.models import User
from app.services.auth import resolve_actor
from app.services.drafts import approve_draft, get_draft, revise_draft
from app.services.hours import approve_by_client, approve_by_supervisor, get_timesheet, get_user, logs_for_week, mark_queried
from app.services.permissions import can_final_approve, can_review_drafts, has_manager_access
from app.services.scores import save_score
from app.services.users import decrypt_hourly_rate
from app.utils.formatters import render_timesheet_table
from app.utils.telegram import timesheet_client_keyboard


async def timesheet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, action, timesheet_id_s = query.data.split(':', 2)
    timesheet_id = int(timesheet_id_s)
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role_user_id is None:
            await query.edit_message_text('Actor not registered in this group.')
            return
        timesheet = await get_timesheet(session, timesheet_id=timesheet_id, client_id=actor.client_id)
        if not timesheet:
            await query.edit_message_text('Timesheet not found in this group.')
            return
        va = await get_user(session, user_id=timesheet.va_id, client_id=actor.client_id)
        if action == 'sup_approve':
            if not has_manager_access(actor.role):
                await query.answer('Only supervisors or business managers can approve at this step.', show_alert=True)
                return
            if timesheet.status != TimesheetStatus.SUBMITTED:
                await query.answer('This timesheet is not waiting for manager review.', show_alert=True)
                return
            await approve_by_supervisor(session, timesheet=timesheet, supervisor_id=actor.role_user_id)
            await session.commit()
            rate = decrypt_hourly_rate(va) if va else None
            logs = await logs_for_week(session, va_id=timesheet.va_id, client_id=timesheet.client_id, week_start=timesheet.week_start_date)
            text = render_timesheet_table(va.display_name if va else 'VA', timesheet.week_start_date, logs, rate)
            client_user = await session.scalar(select(User).where(User.client_id == actor.client_id, User.role.in_([Role.CLIENT, Role.BUSINESS_MANAGER])).order_by(User.id.asc()))
            if client_user:
                await context.bot.send_message(chat_id=client_user.telegram_user_id, text='A timesheet is ready for your final approval.\n\n' + text, reply_markup=timesheet_client_keyboard(timesheet.id))
            await query.edit_message_text(query.message.text + '\n\nApproved and sent to client ✓')
            return
        if action == 'client_approve':
            if not can_final_approve(actor.role):
                await query.answer('Only the client or business manager can give final approval.', show_alert=True)
                return
            if timesheet.status != TimesheetStatus.CLIENT_PENDING:
                await query.answer('This timesheet is not waiting for final approval.', show_alert=True)
                return
            await approve_by_client(session, timesheet=timesheet, client_user_id=actor.role_user_id)
            await session.commit()
            await query.edit_message_text(query.message.text + '\n\nFinal approval complete ✓')
            return
        if action == 'query':
            if actor.role not in {Role.CLIENT, Role.SUPERVISOR, Role.BUSINESS_MANAGER}:
                await query.answer('You cannot query this timesheet.', show_alert=True)
                return
            await mark_queried(session, timesheet=timesheet, actor_id=actor.role_user_id, note='Question raised from inline button.')
            await session.commit()
            await query.edit_message_text(query.message.text + '\n\nMarked as queried. Please follow up.')


async def draft_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, action, draft_id_s = query.data.split(':', 2)
    draft_id = int(draft_id_s)
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role_user_id is None:
            await query.edit_message_text('Draft not found or actor not registered.')
            return
        draft = await get_draft(session, draft_id=draft_id, client_id=actor.client_id)
        if not draft:
            await query.edit_message_text('Draft not found in this group.')
            return
        if not can_review_drafts(actor.role):
            await query.answer('Only the client, supervisor, or business manager can review drafts.', show_alert=True)
            return
        va = await session.scalar(select(User).where(User.id == draft.va_id, User.client_id == actor.client_id))
        if action == 'approve':
            await approve_draft(session, draft=draft, actor_id=actor.role_user_id)
            await session.commit()
            if va:
                await context.bot.send_message(chat_id=va.telegram_user_id, text=f'{draft.draft_code} was approved.')
            await query.edit_message_text(query.message.text + '\n\nApproved ✓')
            return
        if action == 'revise':
            await revise_draft(session, draft=draft, actor_id=actor.role_user_id, note='Revision requested from inline button')
            await session.commit()
            if va:
                await context.bot.send_message(chat_id=va.telegram_user_id, text=f'{draft.draft_code} needs a revision.')
            await query.edit_message_text(query.message.text + '\n\nRevision requested.')
            return


async def score_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, target, score_s = query.data.split(':', 2)
    client_id_s, period_label, trigger = target.split(':', 2)
    score = int(score_s)
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor or actor.role not in {Role.CLIENT, Role.BUSINESS_MANAGER} or actor.role_user_id is None:
            await query.answer('Only the client or business manager can respond.', show_alert=True)
            return
        if int(client_id_s) != actor.client_id:
            await query.answer('This score request belongs to another group.', show_alert=True)
            return
        await save_score(
            session,
            client_id=int(client_id_s),
            va_id=None,
            score=score,
            comment=None,
            trigger_type=ScoreTrigger.MANUAL if trigger == 'manual' else ScoreTrigger.MONTHLY,
            period_label=period_label,
            actor_id=actor.role_user_id,
        )
        await session.commit()
        await query.edit_message_text(f'Thank you. Score recorded: {score}/5.')
