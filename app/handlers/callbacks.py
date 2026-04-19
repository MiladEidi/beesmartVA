from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.enums import Role, ScoreTrigger, TimesheetStatus
from app.models import User
from app.services.auth import resolve_actor
from app.services.drafts import client_approve_draft, get_draft, revise_draft, supervisor_approve_draft
from app.services.hours import approve_by_client, approve_by_supervisor, get_timesheet, get_user, logs_for_week, mark_queried
from app.services.permissions import can_final_approve, has_manager_access
from app.services.scores import save_score
from app.services.users import decrypt_hourly_rate
from app.utils.formatters import render_timesheet_table
from app.utils.telegram import draft_client_keyboard, timesheet_client_keyboard


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
            # Supervisor/BM sees rate; client sees timesheet without rate (confidential)
            supervisor_text = render_timesheet_table(va.display_name if va else 'VA', timesheet.week_start_date, logs, rate)
            client_text = render_timesheet_table(va.display_name if va else 'VA', timesheet.week_start_date, logs, None)
            client_user = await session.scalar(select(User).where(User.client_id == actor.client_id, User.role.in_([Role.CLIENT, Role.BUSINESS_MANAGER])).order_by(User.id.asc()))
            if client_user:
                await context.bot.send_message(chat_id=client_user.telegram_user_id, text='📋 A timesheet is ready for your final approval.\n\n' + client_text, reply_markup=timesheet_client_keyboard(timesheet.id))
            await query.edit_message_text(
                query.message.text + '\n\n✅ Approved and sent to client for final sign-off.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('📋 View pending timesheets — /timesheets', callback_data='ui:backtomenu')],
                ]),
            )
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
            await query.edit_message_text(
                query.message.text + '\n\n✅ Final approval complete. Timesheet is now approved.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('📊 View Reports', callback_data='ui:reports')],
                ]),
            )
            return
        if action == 'query':
            if actor.role not in {Role.CLIENT, Role.SUPERVISOR, Role.BUSINESS_MANAGER}:
                await query.answer('You cannot query this timesheet.', show_alert=True)
                return
            await mark_queried(session, timesheet=timesheet, actor_id=actor.role_user_id, note='Question raised from inline button.')
            await session.commit()
            await query.edit_message_text(
                query.message.text + '\n\n❓ Marked as queried — the VA has been notified to follow up.',
            )


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
        va = await session.scalar(select(User).where(User.id == draft.va_id, User.client_id == actor.client_id))

        # ── Step 1: Supervisor approves → moves to CLIENT_PENDING ──────────────
        if action == 'approve':
            if not has_manager_access(actor.role):
                await query.answer('Only supervisors or business managers can approve at this step.', show_alert=True)
                return
            if draft.status.value != 'PENDING':
                await query.answer('This draft is not waiting for supervisor review.', show_alert=True)
                return
            await supervisor_approve_draft(session, draft=draft, actor_id=actor.role_user_id)
            await session.commit()
            # Find a client user and notify them
            client_user = await session.scalar(
                select(User).where(
                    User.client_id == actor.client_id,
                    User.role.in_([Role.CLIENT, Role.BUSINESS_MANAGER]),
                ).order_by(User.id.asc())
            )
            if client_user:
                try:
                    await context.bot.send_message(
                        chat_id=client_user.telegram_user_id,
                        text=(
                            f'📝 A content draft is ready for your review.\n\n'
                            f'Draft: {draft.draft_code}\n'
                            f'Platform: {draft.platform}\n\n'
                            f'{draft.content_text}\n\n'
                            f'Please approve or request changes using the buttons below.'
                        ),
                        reply_markup=draft_client_keyboard(draft.id),
                    )
                    await query.edit_message_text(
                        query.message.text + '\n\n✅ Approved and sent to the client for final sign-off.',
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton('📝 View all drafts — /drafts', callback_data='ui:backtomenu')],
                        ]),
                    )
                except Exception:
                    await query.edit_message_text(
                        query.message.text + (
                            '\n\n✅ Draft approved — but the client could not be notified automatically.\n'
                            'They may not have started the bot in private chat yet.\n'
                            'Ask them to open a private chat with this bot and send /start.'
                        ),
                    )
            else:
                await query.edit_message_text(
                    query.message.text + '\n\n✅ Draft approved — no client user found to notify.',
                )
            return

        # ── Step 1 revision: Supervisor requests revision ───────────────────────
        if action == 'revise':
            if not has_manager_access(actor.role):
                await query.answer('Only supervisors or business managers can request revisions at this step.', show_alert=True)
                return
            if draft.status.value != 'PENDING':
                await query.answer('This draft is not waiting for supervisor review.', show_alert=True)
                return
            await revise_draft(session, draft=draft, actor_id=actor.role_user_id, note='Revision requested from inline button')
            await session.commit()
            if va:
                await context.bot.send_message(
                    chat_id=va.telegram_user_id,
                    text=(
                        f'✏️ {draft.draft_code} needs a revision before it goes to the client.\n\n'
                        f'Please update the content and resubmit with /draft {draft.platform} [updated content]'
                    ),
                )
            await query.edit_message_text(
                query.message.text + '\n\n✏️ Revision requested — the VA has been notified.',
            )
            return

        # ── Step 2: Client approves → draft is ready to post ───────────────────
        if action == 'client_approve':
            if not can_final_approve(actor.role):
                await query.answer('Only the client or business manager can give final approval.', show_alert=True)
                return
            if draft.status.value != 'CLIENT_PENDING':
                await query.answer('This draft is not waiting for your review.', show_alert=True)
                return
            await client_approve_draft(session, draft=draft, actor_id=actor.role_user_id)
            await session.commit()
            if va:
                await context.bot.send_message(
                    chat_id=va.telegram_user_id,
                    text=(
                        f'🎉 {draft.draft_code} has been approved by the client and is ready to post!\n\n'
                        f'Mark it as published once it\'s live:\n'
                        f'  /posted {draft.draft_code}'
                    ),
                )
            await query.edit_message_text(
                query.message.text + '\n\n✅ Approved! The VA has been notified and will publish the content.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('📝 View all drafts — /drafts', callback_data='ui:report:drafts')],
                ]),
            )
            return

        # ── Step 2 revision: Client requests revision ────────────────────────
        if action == 'client_revise':
            if not can_final_approve(actor.role):
                await query.answer('Only the client or business manager can request revisions at this step.', show_alert=True)
                return
            if draft.status.value != 'CLIENT_PENDING':
                await query.answer('This draft is not waiting for your review.', show_alert=True)
                return
            await revise_draft(session, draft=draft, actor_id=actor.role_user_id, note='Client requested revision')
            await session.commit()
            if va:
                await context.bot.send_message(
                    chat_id=va.telegram_user_id,
                    text=(
                        f'✏️ The client has requested changes to {draft.draft_code}.\n\n'
                        f'Please revise the content and resubmit:\n'
                        f'  /draft {draft.platform} [updated content]'
                    ),
                )
            await query.edit_message_text(
                query.message.text + '\n\n✏️ Revision requested — the VA has been notified to update the content.',
            )
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
        labels = {1: 'Poor 😕', 2: 'Okay 😐', 3: 'Good 🙂', 4: 'Great 😊', 5: 'Excellent 🌟'}
        await query.edit_message_text(
            f'Thank you! Score recorded: {score}/5 — {labels.get(score, "")}',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('📊 View score history — type /scores', callback_data='ui:report:scores')],
            ]),
        )
