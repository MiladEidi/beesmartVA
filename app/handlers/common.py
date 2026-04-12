from telegram import Update
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.enums import Role
from app.services.auth import resolve_actor
from app.services.users import decrypt_credentials, get_client_by_chat_id
from app.utils.dates import format_schedule
from app.utils.telegram import role_main_keyboard

GENERAL_GUIDE = (
    'BeeSmartVA Team Bot\n\n'
    'This bot is built for VA teams and client workspaces in Telegram. It supports group setup, task tracking, hour logging, 3-stage timesheets, draft approvals, follow-up tracking, reporting, invoicing reminders, and satisfaction scoring.\n\n'
    'How to start:\n'
    '1. Add the bot to a Telegram group.\n'
    '2. Run /setup in the group to create the client workspace.\n'
    '3. Use /menu for guided button workflows.\n'
    '4. Use /help or /guide for role-specific process instructions.\n\n'
    'Key workflows:\n'
    '- VAs: log hours, create tasks, submit drafts, log connections, and submit timesheets.\n'
    '- Supervisors: review timesheets, approve drafts, manage users, set rates, and monitor operations.\n'
    '- Clients: approve timesheets, review drafts, and view weekly/monthly summaries.\n'
    '- Business Managers: full access to manage the client workspace and receive executive reports.\n\n'
    'Useful commands: /menu, /help, /weekly, /monthly, /report all, /timesheets, /submit hours, /stats'
)

ROLE_HELP = {
    Role.VA: (
        'VA guide:\n'
        '- Use /menu and tap Log hours to choose date, hours, and send a note.\n'
        '- Review your weekly hours and tasks with /myweek.\n'
        '- Submit your timesheet with /submit hours when ready.\n'
        '- Create tasks with /menu -> Create task or /task [description].\n'
        '- Submit drafts with /menu -> Submit draft, choose platform, and send content.\n'
        '- Log connections with /menu -> Log connection, choose platform, then send the prospect name.\n'
        '- Use Quick actions in /menu to ask your supervisor, flag issues, or request confirmation.\n'
        '- Follow-up reminders and timesheet reminders are sent privately to you.\n'
        'Always use /menu first for guided workflows and buttons.'
    ),
    Role.SUPERVISOR: (
        'Supervisor guide:\n'
        '- Review pending timesheets with /timesheets. Approve or query using the buttons the bot sends privately.\n'
        '- Manage the team using /menu -> Add user, Set supervisor, Set rate.\n'
        '- Review drafts privately via bot review buttons before they are posted.\n'
        '- Use /weekly and /monthly for operational summaries and /report all for broader reports.\n'
        '- Use /stats to see team status and follow-up needs.\n'
        '- You receive proactive reminders for timesheets, drafts, and operational action items.\n'
        'Use /menu for guided manager actions and button flows.'
    ),
    Role.CLIENT: (
        'Client guide:\n'
        '- Approve or reject timesheets using the private Telegram buttons sent when a timesheet is ready.\n'
        '- Review draft submissions privately and approve content before posting.\n'
        '- Use /weekly and /monthly to see summary reports of completed work, meetings, and pending approvals.\n'
        '- Respond to satisfaction check-ins using the buttons sent by the bot.\n'
        '- You receive private reminders when timesheets require your final approval.\n'
        'Use /menu or /help for the latest client workflow guidance.'
    ),
    Role.BUSINESS_MANAGER: (
        'Business Manager guide:\n'
        '- Full workspace access: do supervisor actions and also perform client approvals.\n'
        '- Review executive summaries with /report all and weekly/monthly reports with /weekly and /monthly.\n'
        '- Manage users, assign supervisors, set hourly rates, and oversee task and draft workflows.\n'
        '- Monitor timesheets, draft reviews, and follow-up activity.\n'
        '- Use /menu to access guided management workflows and buttons.\n'
        'This role combines operational control with strategic reporting.'
    ),
}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        role = actor.role if actor else None
    await update.message.reply_text('BeeSmartVA is ready. Use /menu for guided actions or the keyboard below.', reply_markup=role_main_keyboard(role))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        role = actor.role if actor else None
    if role is None:
        await update.message.reply_text(GENERAL_GUIDE, reply_markup=role_main_keyboard(None))
        return
    await update.message.reply_text(ROLE_HELP[role], reply_markup=role_main_keyboard(role))


async def guide_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await help_command(update, context)


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        client = await get_client_by_chat_id(session, update.effective_chat.id)
        if not actor or not client:
            await update.message.reply_text('This group has not been set up yet.')
            return
        await update.message.reply_text(f'Name: {actor.display_name}\nRole: {actor.role.value if actor.role else "Unregistered"}\nClient: {client.name}\nTimezone: {client.timezone}')


async def links_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        client = await get_client_by_chat_id(session, update.effective_chat.id)
        if not client:
            await update.message.reply_text('This group has not been set up yet.')
            return
        links = client.booking_links or []
        await update.message.reply_text('\n'.join(links) if links else 'No booking links set.')


async def contacts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        client = await get_client_by_chat_id(session, update.effective_chat.id)
        if not client:
            await update.message.reply_text('This group has not been set up yet.')
            return
        items = client.restricted_contacts or []
        await update.message.reply_text('\n'.join(items) if items else 'No restricted contacts stored.')


async def prefs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        client = await get_client_by_chat_id(session, update.effective_chat.id)
        if not client:
            await update.message.reply_text('This group has not been set up yet.')
            return
        await update.message.reply_text(str(client.preferences or {}))


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        if not actor:
            await update.message.reply_text('This group has not been set up yet.')
            return
        await update.message.reply_text('Schedule view is configured per user when stored.\n' + format_schedule({}))


async def credentials_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        client = await get_client_by_chat_id(session, update.effective_chat.id)
        actor = await resolve_actor(session, update)
        if not client or not actor or actor.role not in {Role.SUPERVISOR, Role.BUSINESS_MANAGER}:
            await update.message.reply_text('Only supervisors or business managers can view stored credentials.')
            return
        value = decrypt_credentials(client)
        await update.message.reply_text(value or 'No encrypted credentials stored.')
