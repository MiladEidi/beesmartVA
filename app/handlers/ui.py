from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.enums import Role, FlagReason
from app.models import User
from app.services.auth import resolve_actor
from app.services.drafts import submit_draft
from app.services.followups import create_connection, pending_followups
from app.services.hours import get_user, log_hours
from app.services.permissions import has_manager_access
from app.services.tasks import assign_task, complete_task, create_task, flag_task, list_open_tasks
from app.services.users import add_or_update_user, get_role_users, get_user_by_internal_id, set_supervisor
from app.utils.dates import parse_date_maybe

FLOW_KEY = 'guided_flow'


def _menu_keyboard(role: Role | None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton('Profile', callback_data='ui:profile')]]
    if role == Role.VA:
        rows += [
            [InlineKeyboardButton('Log hours', callback_data='ui:hours:start'), InlineKeyboardButton('Create task', callback_data='ui:task:start')],
            [InlineKeyboardButton('Submit draft', callback_data='ui:draft:start')],
            [InlineKeyboardButton('My tasks', callback_data='ui:mytasks:view'), InlineKeyboardButton('Log connection', callback_data='ui:connection:start')],
            [InlineKeyboardButton('Quick actions', callback_data='ui:quickactions:start')],
        ]
    if role in {Role.SUPERVISOR, Role.BUSINESS_MANAGER}:
        rows += [
            [InlineKeyboardButton('Add user', callback_data='ui:adduser:start')],
            [InlineKeyboardButton('Set supervisor', callback_data='ui:setsupervisor:start')],
            [InlineKeyboardButton('Set rate', callback_data='ui:setrate:start')],
        ]
        if role == Role.SUPERVISOR:
            rows += [[InlineKeyboardButton('Pending tasks', callback_data='ui:teamtasks:view')]]
        rows += [[InlineKeyboardButton('Executive report', callback_data='ui:report:all')]]
    if role in {Role.CLIENT, Role.BUSINESS_MANAGER}:
        rows += [[InlineKeyboardButton('Reports', callback_data='ui:reports')]]
    rows += [[InlineKeyboardButton('Cancel', callback_data='ui:cancel')]]
    return InlineKeyboardMarkup(rows)


def _user_button_rows(users: list[User], prefix: str, label_fn=None) -> list[list[InlineKeyboardButton]]:
    label_fn = label_fn or (lambda u: f"{u.display_name} · #{u.id}")
    rows = []
    chunk = []
    for user in users:
        chunk.append(InlineKeyboardButton(label_fn(user), callback_data=f'{prefix}:{user.id}'))
        if len(chunk) == 2:
            rows.append(chunk)
            chunk = []
    if chunk:
        rows.append(chunk)
    rows.append([InlineKeyboardButton('Cancel', callback_data='ui:cancel')])
    return rows


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        role = actor.role if actor else None
    await update.message.reply_text('Choose an action:', reply_markup=_menu_keyboard(role))


async def ui_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(':')
    action = parts[1]
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if action == 'cancel':
            context.user_data.pop(FLOW_KEY, None)
            await query.edit_message_text('Cancelled.')
            return
        if not actor:
            await query.edit_message_text('This group has not been set up yet.')
            return
        if action == 'profile':
            await query.edit_message_text(f'You are {actor.display_name} ({actor.role.value if actor.role else "UNREGISTERED"}) in client #{actor.client_id}.')
            return
        if action == 'reports':
            await query.edit_message_text('Use /weekly or /monthly to get the latest summaries.')
            return
        if action == 'report' and len(parts) > 2 and parts[2] == 'all':
            await query.edit_message_text('Use /report all and the report will be sent to your private chat.')
            return
        if action == 'hours':
            if actor.role != Role.VA or actor.role_user_id is None:
                await query.edit_message_text('Only VAs can log hours.')
                return
            sub = parts[2]
            if sub == 'start':
                context.user_data[FLOW_KEY] = {'type': 'hours'}
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton('Today', callback_data='ui:hoursdate:today'), InlineKeyboardButton('Yesterday', callback_data='ui:hoursdate:yesterday')],
                    [InlineKeyboardButton('Cancel', callback_data='ui:cancel')],
                ])
                await query.edit_message_text('Choose the work date.', reply_markup=kb)
                return
        if action == 'hoursdate':
            flow = context.user_data.get(FLOW_KEY)
            if not flow or flow.get('type') != 'hours':
                await query.edit_message_text('No active hours flow. Start again from /menu.')
                return
            flow['date_token'] = parts[2]
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton('0.5h', callback_data='ui:hourqty:0.5'), InlineKeyboardButton('1h', callback_data='ui:hourqty:1')],
                [InlineKeyboardButton('2h', callback_data='ui:hourqty:2'), InlineKeyboardButton('4h', callback_data='ui:hourqty:4')],
                [InlineKeyboardButton('8h', callback_data='ui:hourqty:8')],
                [InlineKeyboardButton('Cancel', callback_data='ui:cancel')],
            ])
            await query.edit_message_text('Choose the number of hours.', reply_markup=kb)
            return
        if action == 'hourqty':
            flow = context.user_data.get(FLOW_KEY)
            if not flow or flow.get('type') != 'hours' or actor.role_user_id is None:
                await query.edit_message_text('No active hours flow. Start again from /menu.')
                return
            flow['hours'] = parts[2]
            flow['awaiting'] = 'hours_note'
            await query.edit_message_text('Send one short note for this work entry. Example: LinkedIn outreach')
            return
        if action == 'task':
            if actor.role_user_id is None:
                await query.edit_message_text('You are not registered in this group.')
                return
            sub = parts[2]
            if sub == 'start':
                context.user_data[FLOW_KEY] = {'type': 'task', 'assigned_to': actor.role_user_id}
                await query.edit_message_text('Send the task description as one message.')
                return
        if action == 'draft':
            if actor.role != Role.VA or actor.role_user_id is None:
                await query.edit_message_text('Only VAs can submit drafts.')
                return
            sub = parts[2]
            if sub == 'start':
                context.user_data[FLOW_KEY] = {'type': 'draft'}
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton('LinkedIn', callback_data='ui:draftplatform:linkedin'), InlineKeyboardButton('Email', callback_data='ui:draftplatform:email')],
                    [InlineKeyboardButton('Instagram', callback_data='ui:draftplatform:instagram'), InlineKeyboardButton('Other', callback_data='ui:draftplatform:other')],
                    [InlineKeyboardButton('Cancel', callback_data='ui:cancel')],
                ])
                await query.edit_message_text('Choose the platform.', reply_markup=kb)
                return
        if action == 'draftplatform':
            flow = context.user_data.get(FLOW_KEY)
            if not flow or flow.get('type') != 'draft':
                await query.edit_message_text('No active draft flow. Start again from /menu.')
                return
            flow['platform'] = parts[2]
            flow['awaiting'] = 'draft_content'
            await query.edit_message_text('Send the draft content in one message.')
            return
        if action == 'adduser':
            if not has_manager_access(actor.role):
                await query.edit_message_text('Only supervisors or business managers can add users.')
                return
            context.user_data[FLOW_KEY] = {'type': 'adduser', 'awaiting': 'adduser_tg'}
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton('Add VA', callback_data='ui:adduserrole:VA'), InlineKeyboardButton('Add Supervisor', callback_data='ui:adduserrole:SUPERVISOR')],
                [InlineKeyboardButton('Add Client', callback_data='ui:adduserrole:CLIENT'), InlineKeyboardButton('Add Business Manager', callback_data='ui:adduserrole:BUSINESS_MANAGER')],
                [InlineKeyboardButton('Cancel', callback_data='ui:cancel')],
            ])
            await query.edit_message_text('Choose the role for the new user.', reply_markup=kb)
            return
        if action == 'adduserrole':
            flow = context.user_data.get(FLOW_KEY)
            if not flow or flow.get('type') != 'adduser':
                await query.edit_message_text('No active add-user flow. Start again from /menu.')
                return
            flow['role'] = parts[2]
            flow['awaiting'] = 'adduser_tg'
            await query.edit_message_text('Send the Telegram user ID of the new user.')
            return
        if action == 'setsupervisor':
            if not has_manager_access(actor.role):
                await query.edit_message_text('Only supervisors or business managers can assign supervisors.')
                return
            vas = await get_role_users(session, client_id=actor.client_id, role=Role.VA)
            context.user_data[FLOW_KEY] = {'type': 'setsupervisor'}
            await query.edit_message_text('Choose a VA.', reply_markup=InlineKeyboardMarkup(_user_button_rows(vas, 'ui:setsupervisorva', lambda u: u.display_name)))
            return
        if action == 'setsupervisorva':
            flow = context.user_data.get(FLOW_KEY)
            if not flow or flow.get('type') != 'setsupervisor':
                await query.edit_message_text('No active supervisor assignment flow.')
                return
            flow['va_id'] = int(parts[2])
            sups = await get_role_users(session, client_id=actor.client_id, role=Role.SUPERVISOR)
            bms = await get_role_users(session, client_id=actor.client_id, role=Role.BUSINESS_MANAGER)
            users = sups + [u for u in bms if u.id not in {x.id for x in sups}]
            await query.edit_message_text('Choose the supervisor/business manager.', reply_markup=InlineKeyboardMarkup(_user_button_rows(users, 'ui:setsupervisorto', lambda u: f'{u.display_name} · {u.role.value}')))
            return
        if action == 'setsupervisorto':
            flow = context.user_data.get(FLOW_KEY)
            if not flow or flow.get('type') != 'setsupervisor' or actor.role_user_id is None:
                await query.edit_message_text('No active supervisor assignment flow.')
                return
            va_id = flow['va_id']
            sup_id = int(parts[2])
            va = await set_supervisor(session, client_id=actor.client_id, va_user_id=va_id, supervisor_user_id=sup_id, actor_id=actor.role_user_id)
            await session.commit()
            context.user_data.pop(FLOW_KEY, None)
            await query.edit_message_text(f'{va.display_name if va else "VA"} now reports to user #{sup_id}.')
            return
        if action == 'setrate':
            if not has_manager_access(actor.role):
                await query.edit_message_text('Only supervisors or business managers can set rates.')
                return
            vas = await get_role_users(session, client_id=actor.client_id, role=Role.VA)
            context.user_data[FLOW_KEY] = {'type': 'setrate'}
            await query.edit_message_text('Choose a VA.', reply_markup=InlineKeyboardMarkup(_user_button_rows(vas, 'ui:setrateva', lambda u: u.display_name)))
            return
        if action == 'setrateva':
            flow = context.user_data.get(FLOW_KEY)
            if not flow or flow.get('type') != 'setrate':
                await query.edit_message_text('No active rate flow.')
                return
            flow['va_id'] = int(parts[2])
            flow['awaiting'] = 'setrate_amount'
            await query.edit_message_text('Send the hourly rate, for example 12.5')
            return
        if action == 'mytasks':
            if not actor or actor.role_user_id is None:
                await query.edit_message_text('You are not registered in this group.')
                return
            tasks = await list_open_tasks(session, client_id=actor.client_id)
            user_tasks = [t for t in tasks if t.assigned_to == actor.role_user_id]
            if not user_tasks:
                await query.edit_message_text('No tasks assigned to you. Good work! 🎉')
                return
            rows = []
            for task in user_tasks[:15]:
                button_label = f"#{task.id} {task.description[:25]}{'...' if len(task.description) > 25 else ''}"
                rows.append([InlineKeyboardButton(button_label, callback_data=f'ui:taskmenu:{task.id}')])
            rows.append([InlineKeyboardButton('Back to menu', callback_data='ui:cancel')])
            await query.edit_message_text('Your tasks:', reply_markup=InlineKeyboardMarkup(rows))
            return
        if action == 'taskmenu':
            if not actor or actor.role_user_id is None:
                await query.edit_message_text('Not registered.')
                return
            task_id = int(parts[2])
            tasks = await list_open_tasks(session, client_id=actor.client_id)
            task = next((t for t in tasks if t.id == task_id), None)
            if not task:
                await query.edit_message_text('Task not found.')
                return
            text = f"Task #{task.id}\n{task.description}\n\nStatus: {task.status.value}"
            rows = [
                [InlineKeyboardButton('✅ Mark Done', callback_data=f'ui:taskdone:{task.id}')],
                [InlineKeyboardButton('⚠️ Can\'t Do - Skill', callback_data=f'ui:taskflag:{task.id}:skill')],
                [InlineKeyboardButton('⏱️ Can\'t Do - Time', callback_data=f'ui:taskflag:{task.id}:time')],
                [InlineKeyboardButton('Back', callback_data='ui:mytasks:view')],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))
            return
        if action == 'taskdone':
            if not actor or actor.role_user_id is None:
                await query.edit_message_text('Not registered.')
                return
            task_id = int(parts[2])
            task = await complete_task(session, client_id=actor.client_id, task_id=task_id, actor_id=actor.role_user_id)
            await session.commit()
            await query.edit_message_text(f'✅ Task #{task_id} marked as done!')
            return
        if action == 'taskflag':
            if not actor or actor.role != Role.VA or actor.role_user_id is None:
                await query.edit_message_text('Only VAs can flag tasks.')
                return
            task_id = int(parts[2])
            reason = FlagReason(parts[3])
            task = await flag_task(session, client_id=actor.client_id, task_id=task_id, actor_id=actor.role_user_id, reason=reason, note=None)
            await session.commit()
            await query.edit_message_text(f'⚠️ Task #{task_id} flagged as {reason.value}. Your supervisor will review it.')
            return
        if action == 'connection':
            if not actor or actor.role != Role.VA or actor.role_user_id is None:
                await query.edit_message_text('Only VAs can log connections.')
                return
            sub = parts[2]
            if sub == 'start':
                context.user_data[FLOW_KEY] = {'type': 'connection'}
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton('LinkedIn', callback_data='ui:connplatform:LinkedIn'), InlineKeyboardButton('Email', callback_data='ui:connplatform:Email')],
                    [InlineKeyboardButton('Phone', callback_data='ui:connplatform:Phone'), InlineKeyboardButton('Other', callback_data='ui:connplatform:Other')],
                    [InlineKeyboardButton('Cancel', callback_data='ui:cancel')],
                ])
                await query.edit_message_text('Choose platform for connection:', reply_markup=kb)
                return
        if action == 'connplatform':
            flow = context.user_data.get(FLOW_KEY)
            if not flow or flow.get('type') != 'connection':
                await query.edit_message_text('No active connection flow.')
                return
            flow['platform'] = parts[2]
            flow['awaiting'] = 'conn_name'
            await query.edit_message_text('Send the prospect name (first name is enough).')
            return
        if action == 'quickactions':
            if not actor or actor.role != Role.VA:
                await query.edit_message_text('Only VAs have quick actions.')
                return
            rows = [
                [InlineKeyboardButton('❓ Ask Supervisor', callback_data='ui:quickask:start')],
                [InlineKeyboardButton('🚩 Flag Issue', callback_data='ui:quickflag:start')],
                [InlineKeyboardButton('🖐️ Need Confirmation', callback_data='ui:quickconfirm:start')],
                [InlineKeyboardButton('Back to menu', callback_data='ui:cancel')],
            ]
            await query.edit_message_text('Quick actions:', reply_markup=InlineKeyboardMarkup(rows))
            return
        if action == 'quickask':
            context.user_data[FLOW_KEY] = {'type': 'quickask'}
            context.user_data[FLOW_KEY]['awaiting'] = 'quickask_msg'
            await query.edit_message_text('Send your question to your supervisor (one message).')
            return
        if action == 'quickflag':
            context.user_data[FLOW_KEY] = {'type': 'quickflag'}
            context.user_data[FLOW_KEY]['awaiting'] = 'quickflag_msg'
            await query.edit_message_text('Send a note about the issue (one message).')
            return
        if action == 'quickconfirm':
            context.user_data[FLOW_KEY] = {'type': 'quickconfirm'}
            context.user_data[FLOW_KEY]['awaiting'] = 'quickconfirm_msg'
            await query.edit_message_text('Send your confirmation question (one message).')
            return
        if action == 'teamtasks':
            if not actor or not has_manager_access(actor.role):
                await query.edit_message_text('Only supervisors/managers can view team tasks.')
                return
            tasks = await list_open_tasks(session, client_id=actor.client_id)
            if not tasks:
                await query.edit_message_text('No open tasks.')
                return
            rows = []
            for task in tasks[:15]:
                assignee = f" [{task.assigned_to or 'unassigned'}]" if task.assigned_to else " [unassigned]"
                button_label = f"#{task.id}{assignee} {task.description[:20]}{'...' if len(task.description) > 20 else ''}"
                rows.append([InlineKeyboardButton(button_label, callback_data=f'ui:teamtaskmenu:{task.id}')])
            rows.append([InlineKeyboardButton('Back to menu', callback_data='ui:cancel')])
            await query.edit_message_text('Team tasks:', reply_markup=InlineKeyboardMarkup(rows))
            return
        if action == 'teamtaskmenu':
            if not actor or not has_manager_access(actor.role):
                await query.edit_message_text('Not authorized.')
                return
            task_id = int(parts[2])
            tasks = await list_open_tasks(session, client_id=actor.client_id)
            task = next((t for t in tasks if t.id == task_id), None)
            if not task:
                await query.edit_message_text('Task not found.')
                return
            text = f"Task #{task.id}\n{task.description}\n\nAssigned to: {task.assigned_to or 'unassigned'}\nStatus: {task.status.value}"
            vas = await get_role_users(session, client_id=actor.client_id, role=Role.VA)
            rows = []
            for va in vas[:8]:
                rows.append([InlineKeyboardButton(f'👤 Assign to {va.display_name}', callback_data=f'ui:teamassign:{task.id}:{va.id}')])
            rows.append([InlineKeyboardButton('Back', callback_data='ui:teamtasks:view')])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))
            return
        if action == 'teamassign':
            if not actor or not has_manager_access(actor.role):
                await query.edit_message_text('Not authorized.')
                return
            task_id = int(parts[2])
            va_id = int(parts[3])
            await assign_task(session, client_id=actor.client_id, task_id=task_id, assigned_to=va_id, actor_id=actor.role_user_id)
            await session.commit()
            await query.edit_message_text(f'✅ Task #{task_id} assigned!')
            return
        await query.edit_message_text('Action not recognised.')


async def flow_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    flow = context.user_data.get(FLOW_KEY)
    if not flow or not update.message or not update.message.text:
        return
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor:
            return
        text = update.message.text.strip()
        if flow.get('type') == 'hours' and flow.get('awaiting') == 'hours_note' and actor.role_user_id is not None:
            user = await get_user(session, user_id=actor.role_user_id, client_id=actor.client_id)
            work_date = parse_date_maybe(flow['date_token'], user.timezone)
            await log_hours(session, va_id=actor.role_user_id, client_id=actor.client_id, work_date=work_date, hours=Decimal(flow['hours']), note=text)
            await session.commit()
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text(f'Logged {flow["hours"]}h for {work_date.isoformat()} with note: {text}')
            return
        if flow.get('type') == 'task' and actor.role_user_id is not None:
            task = await create_task(session, client_id=actor.client_id, created_by=actor.role_user_id, description=text, assigned_to=flow.get('assigned_to'))
            await session.commit()
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text(f'Task #{task.id} created.')
            return
        if flow.get('type') == 'draft' and flow.get('awaiting') == 'draft_content' and actor.role_user_id is not None:
            draft = await submit_draft(session, client_id=actor.client_id, va_id=actor.role_user_id, platform=flow['platform'], content=text)
            await session.commit()
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text(f'Draft {draft.draft_code} submitted for review.')
            return
        if flow.get('type') == 'adduser':
            if not has_manager_access(actor.role):
                context.user_data.pop(FLOW_KEY, None)
                return
            if flow.get('awaiting') == 'adduser_tg':
                try:
                    flow['telegram_user_id'] = int(text)
                except ValueError:
                    await update.message.reply_text('Telegram user ID must be numeric.')
                    return
                flow['awaiting'] = 'adduser_name'
                await update.message.reply_text('Now send the display name for this user.')
                return
            if flow.get('awaiting') == 'adduser_name':
                role = Role(flow['role'])
                user = await add_or_update_user(session, client_id=actor.client_id, telegram_user_id=flow['telegram_user_id'], display_name=text, role=role)
                await session.commit()
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text(f'{user.display_name} registered as {user.role.value}. Internal user id: #{user.id}')
                return
        if flow.get('type') == 'connection' and flow.get('awaiting') == 'conn_name' and actor.role_user_id is not None:
            conn = await create_connection(session, client_id=actor.client_id, va_id=actor.role_user_id, prospect_name=text, platform=flow['platform'])
            await session.commit()
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text(f'✅ Connection logged for {conn.prospect_name} on {flow["platform"]}. Follow-up scheduled automatically.')
            return
        if flow.get('type') == 'quickask' and flow.get('awaiting') == 'quickask_msg' and actor.role != Role.VA:
            await update.message.reply_text('❌ Only VAs can ask supervisors.')
            context.user_data.pop(FLOW_KEY, None)
            return
        if flow.get('type') == 'quickask' and flow.get('awaiting') == 'quickask_msg' and actor.role_user_id is not None:
            va = await get_user_by_internal_id(session, client_id=actor.client_id, user_id=actor.role_user_id)
            if not va or not va.supervisor:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('❌ No supervisor assigned to you yet.')
                return
            msg = f'❓ Quick question from {va.display_name}:\n\n{text}'
            await context.bot.send_message(chat_id=va.supervisor.telegram_user_id, text=msg)
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text('❓ Question sent to your supervisor.')
            return
        if flow.get('type') == 'quickflag' and flow.get('awaiting') == 'quickflag_msg' and actor.role != Role.VA:
            await update.message.reply_text('❌ Only VAs can flag issues.')
            context.user_data.pop(FLOW_KEY, None)
            return
        if flow.get('type') == 'quickflag' and flow.get('awaiting') == 'quickflag_msg' and actor.role_user_id is not None:
            va = await get_user_by_internal_id(session, client_id=actor.client_id, user_id=actor.role_user_id)
            if not va or not va.supervisor:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('❌ No supervisor assigned to you yet.')
                return
            msg = f'🚩 Issue flagged by {va.display_name}:\n\n{text}'
            await context.bot.send_message(chat_id=va.supervisor.telegram_user_id, text=msg)
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text('🚩 Issue flagged and sent to your supervisor.')
            return
        if flow.get('type') == 'quickconfirm' and flow.get('awaiting') == 'quickconfirm_msg' and actor.role != Role.VA:
            await update.message.reply_text('❌ Only VAs can request confirmations.')
            context.user_data.pop(FLOW_KEY, None)
            return
        if flow.get('type') == 'quickconfirm' and flow.get('awaiting') == 'quickconfirm_msg' and actor.role_user_id is not None:
            va = await get_user_by_internal_id(session, client_id=actor.client_id, user_id=actor.role_user_id)
            if not va or not va.supervisor:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('❌ No supervisor assigned to you yet.')
                return
            msg = f'🖐️ {va.display_name} needs confirmation:\n\n{text}'
            await context.bot.send_message(chat_id=va.supervisor.telegram_user_id, text=msg)
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text('🖐️ Confirmation request sent to your supervisor.')
            return
        if flow.get('type') == 'setrate' and flow.get('awaiting') == 'setrate_amount':
            try:
                amount = Decimal(text)
            except InvalidOperation:
                await update.message.reply_text('Please send a valid number, for example 12.5')
                return
            va = await get_user_by_internal_id(session, client_id=actor.client_id, user_id=flow['va_id'])
            if not va:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('VA not found.')
                return
            user = await add_or_update_user(session, client_id=actor.client_id, telegram_user_id=va.telegram_user_id, display_name=va.display_name, role=va.role, timezone=va.timezone, working_hours=va.working_hours, supervisor_id=va.supervisor_id, hourly_rate=amount, va_start_date=va.va_start_date)
            await session.commit()
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text(f'Rate updated for {user.display_name}: ${amount}/hr')
            return
        if flow.get('type') == 'connection' and flow.get('awaiting') == 'conn_name':
            conn = await create_connection(session, client_id=actor.client_id, va_id=actor.role_user_id, prospect_name=text, platform=flow['platform'])
            await session.commit()
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text(f'✅ Connection logged for {conn.prospect_name} on {flow["platform"]}. Follow-up scheduled automatically.')
            return
        if flow.get('type') == 'quickask' and flow.get('awaiting') == 'quickask_msg':
            if not actor or actor.role != Role.VA or actor.role_user_id is None:
                context.user_data.pop(FLOW_KEY, None)
                return
            va = await get_user_by_internal_id(session, client_id=actor.client_id, user_id=actor.role_user_id)
            if not va or not va.supervisor:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('No supervisor assigned to you yet.')
                return
            msg = f'❓ Quick question from {va.display_name}:\n\n{text}'
            await context.bot.send_message(chat_id=va.supervisor.telegram_user_id, text=msg)
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text('❓ Question sent to your supervisor.')
            return
        if flow.get('type') == 'quickflag' and flow.get('awaiting') == 'quickflag_msg':
            if not actor or actor.role != Role.VA or actor.role_user_id is None:
                context.user_data.pop(FLOW_KEY, None)
                return
            va = await get_user_by_internal_id(session, client_id=actor.client_id, user_id=actor.role_user_id)
            if not va or not va.supervisor:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('No supervisor assigned to you yet.')
                return
            msg = f'🚩 Issue flagged by {va.display_name}:\n\n{text}'
            await context.bot.send_message(chat_id=va.supervisor.telegram_user_id, text=msg)
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text('🚩 Issue flagged and sent to your supervisor.')
            return
        if flow.get('type') == 'quickconfirm' and flow.get('awaiting') == 'quickconfirm_msg':
            if not actor or actor.role != Role.VA or actor.role_user_id is None:
                context.user_data.pop(FLOW_KEY, None)
                return
            va = await get_user_by_internal_id(session, client_id=actor.client_id, user_id=actor.role_user_id)
            if not va or not va.supervisor:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('No supervisor assigned to you yet.')
                return
            msg = f'✋ {va.display_name} needs confirmation:\n\n{text}'
            await context.bot.send_message(chat_id=va.supervisor.telegram_user_id, text=msg)
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text('✋ Confirmation request sent to your supervisor.')
            return
