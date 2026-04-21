from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.enums import Role, FlagReason
from app.models import User
from app.services.auth import resolve_actor, resolve_actor_private
from app.services.drafts import submit_draft
from app.services.followups import create_connection, pending_followups
from app.services.hours import get_user, log_hours
from app.services.permissions import has_manager_access
from app.services.tasks import assign_task, complete_task, create_task, flag_task, list_open_tasks
from app.services.users import add_or_update_user, get_role_users, get_user_by_internal_id, set_supervisor
from app.utils.dates import parse_date_maybe

TOPIC_GUIDES: dict = {}  # populated lazily to avoid circular import


def _get_topic_guides() -> dict:
    global TOPIC_GUIDES
    if not TOPIC_GUIDES:
        from app.handlers.common import TOPIC_GUIDES as _tg
        TOPIC_GUIDES = _tg
    return TOPIC_GUIDES


def _back_row() -> list:
    return [InlineKeyboardButton('Back to menu', callback_data='ui:backtomenu')]


def _cancel_row() -> list:
    return [InlineKeyboardButton('✖ Cancel', callback_data='ui:cancel')]

FLOW_KEY = 'guided_flow'


def _menu_keyboard(role: Role | None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton('👤 My Profile', callback_data='ui:profile'), InlineKeyboardButton('❓ Help & Guide', callback_data='ui:helpguide')]]
    if role == Role.VA:
        rows += [
            [InlineKeyboardButton('⏱ Log Hours — record today\'s work', callback_data='ui:hours:start')],
            [InlineKeyboardButton('✅ Create Task — add a new work item', callback_data='ui:task:start')],
            [InlineKeyboardButton('📝 Submit Draft — send content for review', callback_data='ui:draft:start')],
            [InlineKeyboardButton('📋 My Tasks — view & act on assigned tasks', callback_data='ui:mytasks:view')],
            [InlineKeyboardButton('🔗 Log Connection — track a prospect', callback_data='ui:connection:start')],
            [InlineKeyboardButton('📤 Submit Timesheet — send week\'s hours', callback_data='ui:submittimesheet')],
            [InlineKeyboardButton('⚡ Quick Actions — message your supervisor', callback_data='ui:quickactions:start')],
        ]
    if role in {Role.SUPERVISOR, Role.MANAGER}:
        rows += [
            [InlineKeyboardButton('➕ Add User — register a new team member', callback_data='ui:adduser:start')],
            [InlineKeyboardButton('👥 Set Supervisor — assign VA\'s manager', callback_data='ui:setsupervisor:start')],
            [InlineKeyboardButton('💰 Set Rate — update VA\'s hourly rate', callback_data='ui:setrate:start')],
        ]
        if role == Role.SUPERVISOR:
            rows += [[InlineKeyboardButton('📋 Pending Tasks — view & assign team tasks', callback_data='ui:teamtasks:view')]]
        rows += [[InlineKeyboardButton('📊 Executive Report — full team summary', callback_data='ui:report:all')]]
    if role in {Role.CLIENT, Role.MANAGER}:
        rows += [[InlineKeyboardButton('📈 Reports — weekly, monthly & scores', callback_data='ui:reports')]]
    return InlineKeyboardMarkup(rows)


def _user_button_rows(users: list[User], prefix: str, label_fn=None) -> list[list[InlineKeyboardButton]]:
    label_fn = label_fn or (lambda u: f"{u.display_name} · #{u.display_id or u.id}")
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
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        role = actor.role if actor else None
    if role is None:
        await update.message.reply_text(
            '⚙️ This group is not set up yet.\n\n'
            'Run /guide setup for step-by-step setup instructions.',
            reply_markup=_menu_keyboard(role),
        )
        return
    await update.message.reply_text(
        f'👋 Hi {actor.display_name if actor else ""}! What would you like to do?\n\n'
        '💡 Tap "Help & Guide" for step-by-step instructions on any feature.',
        reply_markup=_menu_keyboard(role),
    )


async def ui_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(':')
    action = parts[1]
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        # In private chat resolve_actor returns None (no group). Fall back to
        # manager-workspace lookup so rate flows work privately.
        if actor is None and update.effective_chat.type == 'private':
            actor = await resolve_actor_private(session, update)
        if action == 'guide':
            topic = parts[2] if len(parts) > 2 else None
            guides = _get_topic_guides()
            if topic and topic in guides:
                await query.edit_message_text(
                    guides[topic],
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton('◀ All guide topics', callback_data='ui:helpguide')],
                        [_back_row()[0]],
                    ]),
                )
            else:
                await query.edit_message_text(
                    'Guide topic not found.',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('All guide topics', callback_data='ui:helpguide')]]),
                )
            return
        if action == 'cancel':
            context.user_data.pop(FLOW_KEY, None)
            role = actor.role if actor else None
            if role is not None:
                await query.edit_message_text(
                    f'Hi {actor.display_name}! Choose an action below.\n'
                    'Tap "Help & Guide" for step-by-step instructions on any feature.',
                    reply_markup=_menu_keyboard(role),
                )
            else:
                await query.edit_message_text(
                    'This group is not set up yet.\n'
                    'Run /setup to get started, or tap Setup Guide below.',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⚙️ Setup Guide', callback_data='ui:guide:setup')]]),
                )
            return
        if not actor:
            await query.edit_message_text('This group has not been set up yet.')
            return
        if action == 'backtomenu':
            await query.edit_message_text(
                f'Hi {actor.display_name}! Choose an action below.\n'
                'Tap "Help & Guide" for step-by-step instructions on any feature.',
                reply_markup=_menu_keyboard(actor.role),
            )
            return
        if action == 'profile':
            await query.edit_message_text(
                f'👤 Your Profile\n\n'
                f'Name:      {actor.display_name}\n'
                f'Role:      {actor.role.value if actor.role else "UNREGISTERED"}\n'
                f'Client ID: #{actor.client_id}\n\n'
                'Tap Help & Guide for role-specific instructions.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('❓ Help & Guide', callback_data='ui:helpguide')],
                    [_back_row()[0]],
                ]),
            )
            return
        if action == 'helpguide':
            rows = [
                [InlineKeyboardButton('⏱ Hours — log & edit daily work', callback_data='ui:guide:hours')],
                [InlineKeyboardButton('📋 Timesheets — submit & approval flow', callback_data='ui:guide:timesheets')],
                [InlineKeyboardButton('✅ Tasks — create, complete, flag', callback_data='ui:guide:tasks')],
                [InlineKeyboardButton('📝 Drafts — submit content for review', callback_data='ui:guide:drafts')],
                [InlineKeyboardButton('🔗 Follow-ups — track prospect connections', callback_data='ui:guide:connections')],
                [InlineKeyboardButton('⚙️ Setup — workspace configuration', callback_data='ui:guide:setup')],
                [InlineKeyboardButton('💰 Invoicing — generate & track invoices', callback_data='ui:guide:invoicing')],
                [InlineKeyboardButton('📊 Reports — all types & auto-schedule', callback_data='ui:guide:reports')],
                [_back_row()[0]],
            ]
            await query.edit_message_text(
                'Help & Guide\n\nTap a topic for step-by-step instructions:',
                reply_markup=InlineKeyboardMarkup(rows),
            )
            return
        if action == 'submittimesheet':
            if not actor or actor.role != Role.VA or actor.role_user_id is None:
                await query.edit_message_text(
                    'Only VAs can submit timesheets.\n\n'
                    'If you are a VA but seeing this error, contact your Manager.',
                    reply_markup=InlineKeyboardMarkup([[_back_row()[0]]]),
                )
                return
            await query.edit_message_text(
                'Submit Your Timesheet\n\n'
                'Step 1 — Verify your hours are complete:\n'
                '  Type /myweek in the chat to review all logged entries\n\n'
                'Step 2 — Submit when ready:\n'
                '  Type /submit hours in the chat\n\n'
                'The bot sends your timesheet to your supervisor for review.\n'
                'Tap the guide below for the full approval flow.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('📋 Timesheets Guide', callback_data='ui:guide:timesheets')],
                    [_back_row()[0]],
                ]),
            )
            return
        if action == 'reports':
            await query.edit_message_text(
                'Reports\n\nChoose a report type:',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('📅 Weekly summary — type /weekly', callback_data='ui:report:weekly')],
                    [InlineKeyboardButton('📆 Monthly overview — type /monthly', callback_data='ui:report:monthly')],
                    [InlineKeyboardButton('⭐ Satisfaction scores — type /scores', callback_data='ui:report:scores')],
                    [InlineKeyboardButton('📊 Full Reports Guide', callback_data='ui:guide:reports')],
                    [_back_row()[0]],
                ]),
            )
            return
        if action == 'report' and len(parts) > 2:
            sub = parts[2]
            if sub == 'all':
                await query.edit_message_text(
                    '📊 Executive Report\n\n'
                    'Type /report all in the chat to get the full executive summary.\n\n'
                    'Managers also see financial totals across all VAs.',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton('📊 Reports Guide', callback_data='ui:guide:reports')],
                        [_back_row()[0]],
                    ]),
                )
            elif sub == 'weekly':
                await query.edit_message_text(
                    '📅 Weekly Summary\n\n'
                    'Type /weekly in the chat to get this week\'s operational summary.\n\n'
                    'Includes: tasks completed, drafts, connections logged, hours worked.',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton('◀ Back to Reports', callback_data='ui:reports')],
                        [_back_row()[0]],
                    ]),
                )
            elif sub == 'monthly':
                await query.edit_message_text(
                    '📆 Monthly Overview\n\n'
                    'Type /monthly in the chat to get the monthly report.\n\n'
                    'Includes: monthly totals, trends, and team performance summary.',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton('◀ Back to Reports', callback_data='ui:reports')],
                        [_back_row()[0]],
                    ]),
                )
            elif sub == 'scores':
                await query.edit_message_text(
                    '⭐ Satisfaction Scores\n\n'
                    'Type /scores in the chat to view the satisfaction score history.\n\n'
                    'Scores are collected via monthly check-ins and on-demand surveys.',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton('◀ Back to Reports', callback_data='ui:reports')],
                        [_back_row()[0]],
                    ]),
                )
            return
        if action == 'hours':
            if actor.role != Role.VA or actor.role_user_id is None:
                await query.edit_message_text(
                    'Only VAs can log hours.\n\n'
                    'If you are a VA, make sure your Manager has added you with /adduser.'
                )
                return
            sub = parts[2]
            if sub == 'start':
                context.user_data[FLOW_KEY] = {'type': 'hours'}
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton('Today', callback_data='ui:hoursdate:today'), InlineKeyboardButton('Yesterday', callback_data='ui:hoursdate:yesterday')],
                    [_cancel_row()[0]],
                ])
                await query.edit_message_text(
                    'Step 1 of 3 — Log Hours\n\n'
                    'Which day are you logging hours for?\n\n'
                    'Tap Today or Yesterday to continue.',
                    reply_markup=kb,
                )
                return
        if action == 'hoursdate':
            flow = context.user_data.get(FLOW_KEY)
            if not flow or flow.get('type') != 'hours':
                await query.edit_message_text('No active hours flow. Start again from /menu.')
                return
            flow['date_token'] = parts[2]
            day_label = 'today' if parts[2] == 'today' else 'yesterday'
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton('0.5h — 30 minutes', callback_data='ui:hourqty:0.5'), InlineKeyboardButton('1h', callback_data='ui:hourqty:1')],
                [InlineKeyboardButton('2h', callback_data='ui:hourqty:2'), InlineKeyboardButton('4h — half day', callback_data='ui:hourqty:4')],
                [InlineKeyboardButton('6h', callback_data='ui:hourqty:6'), InlineKeyboardButton('8h — full day', callback_data='ui:hourqty:8')],
                [_cancel_row()[0]],
            ])
            await query.edit_message_text(
                f'Step 2 of 3 — Log Hours ({day_label})\n\n'
                'How many hours did you work?\n\n'
                'Tap the closest amount.',
                reply_markup=kb,
            )
            return
        if action == 'hourqty':
            flow = context.user_data.get(FLOW_KEY)
            if not flow or flow.get('type') != 'hours' or actor.role_user_id is None:
                await query.edit_message_text('No active hours flow. Start again from /menu.')
                return
            flow['hours'] = parts[2]
            flow['awaiting'] = 'hours_note'
            await query.edit_message_text(
                f'Step 3 of 3 — Log Hours\n\n'
                f'Hours selected: {parts[2]}h\n\n'
                'Type a short note describing what you worked on, then send it.\n'
                'Example: LinkedIn outreach and email replies',
                reply_markup=InlineKeyboardMarkup([[_cancel_row()[0]]]),
            )
            return
        if action == 'task':
            if actor.role_user_id is None:
                await query.edit_message_text(
                    'You are not registered in this group.\n\n'
                    'Ask your Manager to add you with /adduser.'
                )
                return
            sub = parts[2]
            if sub == 'start':
                context.user_data[FLOW_KEY] = {'type': 'task', 'assigned_to': actor.role_user_id}
                await query.edit_message_text(
                    'Create Task\n\n'
                    'Type the task description and send it as a message.\n\n'
                    'Be specific so it\'s easy to track and mark done later.\n'
                    'Example: Research top 10 LinkedIn hashtags for Q2 campaign',
                    reply_markup=InlineKeyboardMarkup([[_cancel_row()[0]]]),
                )
                return
        if action == 'draft':
            if actor.role != Role.VA or actor.role_user_id is None:
                await query.edit_message_text(
                    'Only VAs can submit drafts.\n\n'
                    'For the full draft guide: /guide drafts'
                )
                return
            sub = parts[2]
            if sub == 'start':
                context.user_data[FLOW_KEY] = {'type': 'draft'}
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton('🔵 LinkedIn', callback_data='ui:draftplatform:linkedin'), InlineKeyboardButton('📧 Email', callback_data='ui:draftplatform:email')],
                    [InlineKeyboardButton('📸 Instagram', callback_data='ui:draftplatform:instagram'), InlineKeyboardButton('🔗 Other', callback_data='ui:draftplatform:other')],
                    [_cancel_row()[0]],
                ])
                await query.edit_message_text(
                    'Step 1 of 2 — Submit Draft\n\n'
                    'Which platform is this content for?\n\n'
                    'Tap your platform — then you\'ll send the full draft content.',
                    reply_markup=kb,
                )
                return
        if action == 'draftplatform':
            flow = context.user_data.get(FLOW_KEY)
            if not flow or flow.get('type') != 'draft':
                await query.edit_message_text('No active draft flow. Start again from /menu.')
                return
            flow['platform'] = parts[2]
            flow['awaiting'] = 'draft_content'
            await query.edit_message_text(
                f'Step 2 of 2 — Submit Draft ({parts[2].capitalize()})\n\n'
                'Type the full draft content and send it as a message.\n\n'
                'Your supervisor will receive it for review and can approve or request changes.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('📖 Drafts Guide', callback_data='ui:guide:drafts')],
                    [_cancel_row()[0]],
                ]),
            )
            return
        if action == 'adduser':
            if not has_manager_access(actor.role):
                await query.edit_message_text(
                    'Only supervisors or managers can add users.\n\n'
                    'For setup help: /guide setup'
                )
                return
            context.user_data[FLOW_KEY] = {'type': 'adduser', 'awaiting': 'adduser_tg'}
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton('🙋 VA — logs hours, tasks, drafts', callback_data='ui:adduserrole:VA')],
                [InlineKeyboardButton('👔 Supervisor — reviews timesheets & drafts', callback_data='ui:adduserrole:SUPERVISOR')],
                [InlineKeyboardButton('👤 Client — final timesheet approval', callback_data='ui:adduserrole:CLIENT')],
                [InlineKeyboardButton('⭐ Manager — full access', callback_data='ui:adduserrole:MANAGER')],
                [_cancel_row()[0]],
            ])
            await query.edit_message_text(
                'Step 1 of 3 — Add User\n\n'
                'Choose the role for the new team member:\n\n'
                'Tip: To find a user\'s Telegram ID, ask them to message @userinfobot — it shows their numeric ID.',
                reply_markup=kb,
            )
            return
        if action == 'adduserrole':
            flow = context.user_data.get(FLOW_KEY)
            if not flow or flow.get('type') != 'adduser':
                await query.edit_message_text('No active add-user flow. Start again from /menu.')
                return
            flow['role'] = parts[2]
            flow['awaiting'] = 'adduser_tg'
            await query.edit_message_text(
                f'Step 2 of 3 — Add User ({parts[2]})\n\n'
                'Type and send the Telegram user ID of the new user.\n\n'
                'How to find it: Ask them to message @userinfobot on Telegram — it replies with their numeric ID.\n'
                'Example: 123456789',
                reply_markup=InlineKeyboardMarkup([[_cancel_row()[0]]]),
            )
            return
        if action == 'setsupervisor':
            if not has_manager_access(actor.role):
                await query.edit_message_text('Only supervisors or managers can assign supervisors.')
                return
            vas = await get_role_users(session, client_id=actor.client_id, role=Role.VA)
            if not vas:
                await query.edit_message_text(
                    'No VAs are registered yet.\n\nAdd one first with /adduser or /menu → Add User.',
                    reply_markup=InlineKeyboardMarkup([[_back_row()[0]]]),
                )
                return
            context.user_data[FLOW_KEY] = {'type': 'setsupervisor'}
            await query.edit_message_text(
                'Step 1 of 2 — Assign Supervisor\n\n'
                'Choose the VA to assign a supervisor to:',
                reply_markup=InlineKeyboardMarkup(_user_button_rows(vas, 'ui:setsupervisorva', lambda u: f'🙋 {u.display_name}')),
            )
            return
        if action == 'setsupervisorva':
            flow = context.user_data.get(FLOW_KEY)
            if not flow or flow.get('type') != 'setsupervisor':
                await query.edit_message_text('No active supervisor assignment flow.')
                return
            flow['va_id'] = int(parts[2])
            sups = await get_role_users(session, client_id=actor.client_id, role=Role.SUPERVISOR)
            bms = await get_role_users(session, client_id=actor.client_id, role=Role.MANAGER)
            users = sups + [u for u in bms if u.id not in {x.id for x in sups}]
            if not users:
                context.user_data.pop(FLOW_KEY, None)
                await query.edit_message_text(
                    'No supervisors or managers are registered yet.\n\nAdd one with /adduser or /menu → Add User.',
                    reply_markup=InlineKeyboardMarkup([[_back_row()[0]]]),
                )
                return
            await query.edit_message_text(
                'Step 2 of 2 — Assign Supervisor\n\n'
                'Choose the supervisor or manager for this VA:',
                reply_markup=InlineKeyboardMarkup(_user_button_rows(users, 'ui:setsupervisorto', lambda u: f'👔 {u.display_name} ({u.role.value})')),
            )
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
            sup_display = (va.supervisor.display_id or va.supervisor.id) if va and va.supervisor else sup_id
            await query.edit_message_text(
                f'✅ {va.display_name if va else "VA"} now reports to user #{sup_display}.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('👥 Set another supervisor', callback_data='ui:setsupervisor:start')],
                    [_back_row()[0]],
                ]),
            )
            return
        if action == 'setrate':
            if update.effective_chat.type != 'private':
                await query.edit_message_text(
                    '⚠️ Rate info is confidential.\n\n'
                    'Please set rates in a private chat with me to protect VA privacy.\n\n'
                    'Open a private chat with this bot, then use /menu → Set Rate\n'
                    'or type: /set rate [va_user_id] [amount]'
                )
                return
            if not has_manager_access(actor.role):
                await query.edit_message_text('Only supervisors or managers can set rates.')
                return
            vas = await get_role_users(session, client_id=actor.client_id, role=Role.VA)
            if not vas:
                await query.edit_message_text(
                    'No VAs are registered yet.\n\nAdd one first with /adduser or /menu → Add User.',
                    reply_markup=InlineKeyboardMarkup([[_back_row()[0]]]),
                )
                return
            context.user_data[FLOW_KEY] = {'type': 'setrate'}
            await query.edit_message_text(
                'Set Hourly Rate\n\n'
                'Choose the VA to update the hourly rate for:',
                reply_markup=InlineKeyboardMarkup(_user_button_rows(vas, 'ui:setrateva', lambda u: f'🙋 {u.display_name}')),
            )
            return
        if action == 'setrateva':
            flow = context.user_data.get(FLOW_KEY)
            if not flow or flow.get('type') != 'setrate':
                await query.edit_message_text('No active rate flow.')
                return
            flow['va_id'] = int(parts[2])
            flow['awaiting'] = 'setrate_amount'
            await query.edit_message_text(
                'Set Hourly Rate\n\n'
                'Type the hourly rate as a number and send it.\n\n'
                'Example: 12.5 (means $12.50 per hour)\n\n'
                'This rate is used for invoice calculations on approved timesheets.',
                reply_markup=InlineKeyboardMarkup([[_cancel_row()[0]]]),
            )
            return
        if action == 'mytasks':
            if not actor or actor.role_user_id is None:
                await query.edit_message_text('You are not registered in this group.')
                return
            tasks = await list_open_tasks(session, client_id=actor.client_id)
            user_tasks = [t for t in tasks if t.assigned_to == actor.role_user_id]
            if not user_tasks:
                await query.edit_message_text(
                    'No tasks assigned to you right now. Great work! 🎉',
                    reply_markup=InlineKeyboardMarkup([[_back_row()[0]]]),
                )
                return
            rows = []
            for task in user_tasks[:15]:
                button_label = f"#{task.id} {task.description[:28]}{'…' if len(task.description) > 28 else ''}"
                rows.append([InlineKeyboardButton(button_label, callback_data=f'ui:taskmenu:{task.id}')])
            rows.append([_back_row()[0]])
            await query.edit_message_text(
                f'Your Tasks ({len(user_tasks)} open)\n\nTap a task to mark it done or flag it:',
                reply_markup=InlineKeyboardMarkup(rows),
            )
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
            text = (
                f'📋 Task #{task.id}\n\n'
                f'{task.description}\n\n'
                f'Status: {task.status.value}'
            )
            rows = [
                [InlineKeyboardButton('✅ Mark Done — I completed this task', callback_data=f'ui:taskdone:{task.id}')],
                [InlineKeyboardButton("⚠️ Can't Do — Missing skill or access", callback_data=f'ui:taskflag:{task.id}:skill')],
                [InlineKeyboardButton("⏱️ Can't Do — Not enough time this week", callback_data=f'ui:taskflag:{task.id}:time')],
                [InlineKeyboardButton('◀ Back to my tasks', callback_data='ui:mytasks:view')],
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
            await query.edit_message_text(
                f'✅ Task #{task_id} marked as done!\n\nGreat work!',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('📋 Back to my tasks', callback_data='ui:mytasks:view')],
                    [_back_row()[0]],
                ]),
            )
            return
        if action == 'taskflag':
            if not actor or actor.role != Role.VA or actor.role_user_id is None:
                await query.edit_message_text('Only VAs can flag tasks.')
                return
            task_id = int(parts[2])
            reason = FlagReason(parts[3])
            task = await flag_task(session, client_id=actor.client_id, task_id=task_id, actor_id=actor.role_user_id, reason=reason, note=None)
            await session.commit()
            await query.edit_message_text(
                f'⚠️ Task #{task_id} flagged as {reason.value}.\n\n'
                'Your supervisor has been notified and can reassign or resolve it.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('📋 Back to my tasks', callback_data='ui:mytasks:view')],
                    [_back_row()[0]],
                ]),
            )
            return
        if action == 'connection':
            if not actor or actor.role != Role.VA or actor.role_user_id is None:
                await query.edit_message_text(
                    'Only VAs can log connections.\n\n'
                    'For the full follow-up guide: /guide connections'
                )
                return
            sub = parts[2]
            if sub == 'start':
                context.user_data[FLOW_KEY] = {'type': 'connection'}
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton('🔵 LinkedIn', callback_data='ui:connplatform:LinkedIn'), InlineKeyboardButton('📧 Email', callback_data='ui:connplatform:Email')],
                    [InlineKeyboardButton('📞 Phone', callback_data='ui:connplatform:Phone'), InlineKeyboardButton('🔗 Other', callback_data='ui:connplatform:Other')],
                    [_cancel_row()[0]],
                ])
                await query.edit_message_text(
                    'Step 1 of 2 — Log Connection\n\n'
                    'Where did you connect with this prospect?\n\n'
                    'A follow-up reminder will be scheduled automatically in 3 days.',
                    reply_markup=kb,
                )
                return
        if action == 'connplatform':
            flow = context.user_data.get(FLOW_KEY)
            if not flow or flow.get('type') != 'connection':
                await query.edit_message_text('No active connection flow.')
                return
            flow['platform'] = parts[2]
            flow['awaiting'] = 'conn_name'
            await query.edit_message_text(
                f'Step 2 of 2 — Log Connection ({parts[2]})\n\n'
                'Type the prospect\'s name and send it.\n\n'
                'Example: Sarah Jones (first name is fine)\n\n'
                'A follow-up reminder will be sent in 3 days.',
                reply_markup=InlineKeyboardMarkup([[_cancel_row()[0]]]),
            )
            return
        if action == 'quickactions':
            if not actor or actor.role != Role.VA:
                await query.edit_message_text('Only VAs have quick actions.')
                return
            rows = [
                [InlineKeyboardButton('❓ Ask — send a question to supervisor', callback_data='ui:quickask:start')],
                [InlineKeyboardButton('🚩 Flag — report a problem or blocker', callback_data='ui:quickflag:start')],
                [InlineKeyboardButton('🖐️ Confirm — get a yes/no decision', callback_data='ui:quickconfirm:start')],
                [_back_row()[0]],
            ]
            await query.edit_message_text(
                'Quick Actions\n\n'
                'Send a message directly to your supervisor — they receive it privately.\n\n'
                '  ❓ Ask — for questions\n'
                '  🚩 Flag — for problems or blockers\n'
                '  🖐️ Confirm — when you need a yes/no decision\n\n'
                'Tap the action type below to continue.',
                reply_markup=InlineKeyboardMarkup(rows),
            )
            return
        if action == 'quickask':
            context.user_data[FLOW_KEY] = {'type': 'quickask', 'awaiting': 'quickask_msg'}
            await query.edit_message_text(
                '❓ Ask Supervisor\n\n'
                'Type your question and send it as a message.\n\n'
                'Your supervisor will receive it privately.\n'
                'Example: Should I prioritise the LinkedIn content or the email campaign today?',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('◀ Back to Quick Actions', callback_data='ui:quickactions:start')],
                    [_cancel_row()[0]],
                ]),
            )
            return
        if action == 'quickflag':
            context.user_data[FLOW_KEY] = {'type': 'quickflag', 'awaiting': 'quickflag_msg'}
            await query.edit_message_text(
                '🚩 Flag Issue\n\n'
                'Describe the issue or blocker you\'re facing — then send it.\n\n'
                'Your supervisor will receive it privately.\n'
                'Example: I don\'t have access to the LinkedIn account — can\'t post today.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('◀ Back to Quick Actions', callback_data='ui:quickactions:start')],
                    [_cancel_row()[0]],
                ]),
            )
            return
        if action == 'quickconfirm':
            context.user_data[FLOW_KEY] = {'type': 'quickconfirm', 'awaiting': 'quickconfirm_msg'}
            await query.edit_message_text(
                '🖐️ Need Confirmation\n\n'
                'Type your yes/no question and send it.\n\n'
                'Your supervisor will receive it privately.\n'
                'Example: Should I send the proposal email today or wait until Thursday?',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('◀ Back to Quick Actions', callback_data='ui:quickactions:start')],
                    [_cancel_row()[0]],
                ]),
            )
            return
        if action == 'teamtasks':
            if not actor or not has_manager_access(actor.role):
                await query.edit_message_text('Only supervisors/managers can view team tasks.')
                return
            tasks = await list_open_tasks(session, client_id=actor.client_id)
            if not tasks:
                await query.edit_message_text(
                    'No open team tasks right now.',
                    reply_markup=InlineKeyboardMarkup([[_back_row()[0]]]),
                )
                return
            rows = []
            for task in tasks[:15]:
                assignee = f'assigned' if task.assigned_to else 'unassigned'
                button_label = f"#{task.id} [{assignee}] {task.description[:22]}{'…' if len(task.description) > 22 else ''}"
                rows.append([InlineKeyboardButton(button_label, callback_data=f'ui:teamtaskmenu:{task.id}')])
            rows.append([_back_row()[0]])
            await query.edit_message_text(
                f'Team Tasks ({len(tasks)} open)\n\nTap a task to assign it to a VA:',
                reply_markup=InlineKeyboardMarkup(rows),
            )
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
            vas = await get_role_users(session, client_id=actor.client_id, role=Role.VA)
            va_names = {va.id: va.display_name for va in vas}
            assigned_label = va_names.get(task.assigned_to, 'Unassigned') if task.assigned_to else 'Unassigned'
            text = (
                f'📋 Task #{task.id}\n\n'
                f'{task.description}\n\n'
                f'Assigned to: {assigned_label}\n'
                f'Status: {task.status.value}\n\n'
                'Tap a VA below to (re)assign this task:'
            )
            if not vas:
                await query.edit_message_text(
                    f'📋 Task #{task.id}\n\n{task.description}\n\nNo VAs are registered yet. Add one with /adduser.',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('◀ Back', callback_data='ui:teamtasks:view')]]),
                )
                return
            rows = []
            for va in vas[:8]:
                rows.append([InlineKeyboardButton(f'🙋 Assign to {va.display_name}', callback_data=f'ui:teamassign:{task.id}:{va.id}')])
            rows.append([InlineKeyboardButton('◀ Back to team tasks', callback_data='ui:teamtasks:view')])
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
            await query.edit_message_text(
                f'✅ Task #{task_id} assigned!\n\nThe VA will be notified.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('📋 Back to team tasks', callback_data='ui:teamtasks:view')],
                    [_back_row()[0]],
                ]),
            )
            return
        await query.edit_message_text('Action not recognised.')


async def flow_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    flow = context.user_data.get(FLOW_KEY)
    if not flow or not update.message or not update.message.text:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if actor is None and update.effective_chat.type == 'private':
            actor = await resolve_actor_private(session, update)
        if not actor:
            return
        text = update.message.text.strip()
        if flow.get('type') == 'hours' and flow.get('awaiting') == 'hours_note' and actor.role_user_id is not None:
            user = await get_user(session, user_id=actor.role_user_id, client_id=actor.client_id)
            work_date = parse_date_maybe(flow['date_token'], user.timezone)
            await log_hours(session, va_id=actor.role_user_id, client_id=actor.client_id, work_date=work_date, hours=Decimal(flow['hours']), note=text)
            await session.commit()
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text(
                f'✅ Hours logged!\n\n'
                f'📅 Date:  {work_date.isoformat()}\n'
                f'⏱ Hours: {flow["hours"]}h\n'
                f'📝 Note:  {text}\n\n'
                '─────────────────────\n'
                'What would you like to do next?',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('⏱ Log more hours', callback_data='ui:hours:start')],
                    [InlineKeyboardButton('📤 Submit Timesheet', callback_data='ui:submittimesheet')],
                    [InlineKeyboardButton('🏠 Back to menu', callback_data='ui:backtomenu')],
                ]),
            )
            return
        if flow.get('type') == 'task' and actor.role_user_id is not None:
            task = await create_task(session, client_id=actor.client_id, created_by=actor.role_user_id, description=text, assigned_to=flow.get('assigned_to'))
            await session.commit()
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text(
                f'✅ Task #{task.id} created!\n\n'
                f'📋 {text}\n\n'
                '─────────────────────\n'
                'Track it from My Tasks whenever you\'re ready.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('📋 View my tasks', callback_data='ui:mytasks:view')],
                    [InlineKeyboardButton('✅ Create another task', callback_data='ui:task:start')],
                    [InlineKeyboardButton('🏠 Back to menu', callback_data='ui:backtomenu')],
                ]),
            )
            return
        if flow.get('type') == 'draft' and flow.get('awaiting') == 'draft_content' and actor.role_user_id is not None:
            draft = await submit_draft(session, client_id=actor.client_id, va_id=actor.role_user_id, platform=flow['platform'], content=text)
            await session.commit()
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text(
                f'✅ Draft submitted for review!\n\n'
                f'🔖 Code:     {draft.draft_code}\n'
                f'📱 Platform: {flow["platform"].capitalize()}\n'
                f'🕐 Status:   Pending review\n\n'
                '─────────────────────\n'
                'Your supervisor will be notified to review it.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('📝 Submit another draft', callback_data='ui:draft:start')],
                    [InlineKeyboardButton('📖 Drafts Guide', callback_data='ui:guide:drafts')],
                    [InlineKeyboardButton('🏠 Back to menu', callback_data='ui:backtomenu')],
                ]),
            )
            return
        if flow.get('type') == 'adduser':
            if not has_manager_access(actor.role):
                context.user_data.pop(FLOW_KEY, None)
                return
            if flow.get('awaiting') == 'adduser_tg':
                try:
                    flow['telegram_user_id'] = int(text)
                except ValueError:
                    await update.message.reply_text(
                        '⚠️ Telegram user ID must be a number.\n\n'
                        'How to find it: Ask the user to message @userinfobot — it shows their numeric ID.'
                    )
                    return
                flow['awaiting'] = 'adduser_name'
                await update.message.reply_text(
                    f'Step 3 of 3 — Add User\n\n'
                    f'✅ Telegram ID: {flow["telegram_user_id"]}\n\n'
                    '📛 Now send the display name for this user.\n'
                    'Example: Sarah Jones'
                )
                return
            if flow.get('awaiting') == 'adduser_name':
                role = Role(flow['role'])
                if role == Role.MANAGER and actor.role != Role.MANAGER:
                    context.user_data.pop(FLOW_KEY, None)
                    await update.message.reply_text(
                        '⛔ Only the current Manager can assign or change the Manager role.'
                    )
                    return
                try:
                    user = await add_or_update_user(
                        session,
                        client_id=actor.client_id,
                        telegram_user_id=flow['telegram_user_id'],
                        display_name=text,
                        role=role,
                        allow_business_manager_transfer=(role == Role.MANAGER and actor.role == Role.MANAGER),
                    )
                except ValueError as exc:
                    context.user_data.pop(FLOW_KEY, None)
                    await update.message.reply_text(str(exc))
                    return
                await session.commit()
                context.user_data.pop(FLOW_KEY, None)
                next_rows = []
                if user.role == Role.VA:
                    next_rows += [
                        [InlineKeyboardButton('👥 Assign their supervisor', callback_data='ui:setsupervisor:start')],
                        [InlineKeyboardButton('💰 Set their hourly rate', callback_data='ui:setrate:start')],
                    ]
                next_rows += [
                    [InlineKeyboardButton('➕ Add another user', callback_data='ui:adduser:start')],
                    [InlineKeyboardButton('🏠 Back to menu', callback_data='ui:backtomenu')],
                ]
                extra = (
                    '👇 Use the buttons below to assign their supervisor and rate.'
                    if user.role == Role.VA else
                    '💬 Ask them to type /start in the group to activate their account.'
                )
                await update.message.reply_text(
                    f'🎉 User added successfully!\n\n'
                    f'👤 Name:     {user.display_name}\n'
                    f'🏷 Role:     {user.role.value}\n'
                    f'🆔 User ID:  #{user.display_id or user.id}\n\n'
                    f'{extra}',
                    reply_markup=InlineKeyboardMarkup(next_rows),
                )
                return
        if flow.get('type') == 'connection' and flow.get('awaiting') == 'conn_name' and actor.role_user_id is not None:
            conn = await create_connection(session, client_id=actor.client_id, va_id=actor.role_user_id, prospect_name=text, platform=flow['platform'])
            await session.commit()
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text(
                f'✅ Connection logged!\n\n'
                f'👤 Name:      {conn.prospect_name}\n'
                f'📱 Platform:  {flow["platform"]}\n\n'
                '─────────────────────\n'
                '⏰ A follow-up reminder will be sent in 3 days.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('🔗 Log another connection', callback_data='ui:connection:start')],
                    [InlineKeyboardButton('📖 Follow-ups Guide', callback_data='ui:guide:connections')],
                    [InlineKeyboardButton('🏠 Back to menu', callback_data='ui:backtomenu')],
                ]),
            )
            return
        _quick_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton('⚡ Back to Quick Actions', callback_data='ui:quickactions:start')],
            [InlineKeyboardButton('🏠 Back to menu', callback_data='ui:backtomenu')],
        ])
        if flow.get('type') == 'quickask' and flow.get('awaiting') == 'quickask_msg':
            if actor.role != Role.VA or actor.role_user_id is None:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('❌ Only VAs can ask supervisors.')
                return
            va = await get_user_by_internal_id(session, client_id=actor.client_id, user_id=actor.role_user_id)
            if not va or not va.supervisor:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('❌ No supervisor assigned to you yet. Contact your Manager.')
                return
            try:
                await context.bot.send_message(chat_id=va.supervisor.telegram_user_id, text=f'❓ Question from {va.display_name}:\n\n{text}')
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('✅ Question sent to your supervisor!\n\nThey\'ll get back to you shortly.', reply_markup=_quick_kb)
            except Exception:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text(
                    f'⚠️ Could not reach your supervisor.\n\n'
                    f'Ask {va.supervisor.display_name} to open a private chat with this bot and send /start — then try again.'
                )
            return
        if flow.get('type') == 'quickflag' and flow.get('awaiting') == 'quickflag_msg':
            if actor.role != Role.VA or actor.role_user_id is None:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('❌ Only VAs can flag issues.')
                return
            va = await get_user_by_internal_id(session, client_id=actor.client_id, user_id=actor.role_user_id)
            if not va or not va.supervisor:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('❌ No supervisor assigned to you yet. Contact your Manager.')
                return
            try:
                await context.bot.send_message(chat_id=va.supervisor.telegram_user_id, text=f'🚩 Issue flagged by {va.display_name}:\n\n{text}')
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('✅ Issue flagged!\n\nYour supervisor has been notified.', reply_markup=_quick_kb)
            except Exception:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text(
                    f'⚠️ Could not reach your supervisor.\n\n'
                    f'Ask {va.supervisor.display_name} to open a private chat with this bot and send /start — then try again.'
                )
            return
        if flow.get('type') == 'quickconfirm' and flow.get('awaiting') == 'quickconfirm_msg':
            if actor.role != Role.VA or actor.role_user_id is None:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('❌ Only VAs can request confirmations.')
                return
            va = await get_user_by_internal_id(session, client_id=actor.client_id, user_id=actor.role_user_id)
            if not va or not va.supervisor:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('❌ No supervisor assigned to you yet. Contact your Manager.')
                return
            try:
                await context.bot.send_message(chat_id=va.supervisor.telegram_user_id, text=f'🖐️ {va.display_name} needs your confirmation:\n\n{text}')
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('✅ Confirmation request sent!\n\nYour supervisor will respond shortly.', reply_markup=_quick_kb)
            except Exception:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text(
                    f'⚠️ Could not reach your supervisor.\n\n'
                    f'Ask {va.supervisor.display_name} to open a private chat with this bot and send /start — then try again.'
                )
            return
        if flow.get('type') == 'setrate' and flow.get('awaiting') == 'setrate_amount':
            try:
                amount = Decimal(text)
            except InvalidOperation:
                await update.message.reply_text('⚠️ Please send a valid number, for example: 12.50')
                return
            if amount <= 0:
                await update.message.reply_text('⚠️ Rate must be greater than zero.')
                return
            va = await get_user_by_internal_id(session, client_id=actor.client_id, user_id=flow['va_id'])
            if not va:
                context.user_data.pop(FLOW_KEY, None)
                await update.message.reply_text('VA not found.')
                return
            user = await add_or_update_user(session, client_id=actor.client_id, telegram_user_id=va.telegram_user_id, display_name=va.display_name, role=va.role, timezone=va.timezone, working_hours=va.working_hours, supervisor_id=va.supervisor_id, hourly_rate=amount, va_start_date=va.va_start_date)
            await session.commit()
            context.user_data.pop(FLOW_KEY, None)
            await update.message.reply_text(
                f'✅ Rate updated!\n\n'
                f'👤 VA: {user.display_name}\n'
                f'💰 New rate: ${amount}/hr',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('💰 Set another rate', callback_data='ui:setrate:start')],
                    [InlineKeyboardButton('🏠 Back to menu', callback_data='ui:backtomenu')],
                ]),
            )
            return
