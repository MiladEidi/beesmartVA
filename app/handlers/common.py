from telegram import Update
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.enums import Role
from app.services.auth import resolve_actor
from app.services.users import decrypt_credentials, get_client_by_chat_id
from app.utils.dates import format_schedule
from app.utils.telegram import role_main_keyboard

GENERAL_GUIDE = (
    'BeeSmartVA — Getting Started\n\n'
    'This bot manages VA team workflows: hour logging, timesheets, task tracking, '
    'draft approvals, follow-up reminders, invoicing, and reporting.\n\n'
    'FIRST-TIME SETUP (in a Telegram group):\n'
    '  1. Add the bot to your group\n'
    '  2. Run /setup with your workspace details (see /guide setup)\n'
    '  3. Add team members with /adduser or /menu → Add user\n'
    '  4. Assign supervisors with /set supervisor\n'
    '  5. Each team member types /start in the group\n\n'
    'QUICK NAVIGATION:\n'
    '  /menu        → Guided button flows for all actions\n'
    '  /help        → Role-specific quick reference\n'
    '  /guide       → Detailed step-by-step guide for your role\n'
    '  /guide [topic] → Guide for a specific topic (see list below)\n\n'
    'AVAILABLE GUIDE TOPICS:\n'
    '  /guide hours       → How to log and edit work hours\n'
    '  /guide timesheets  → Full timesheet submission and approval flow\n'
    '  /guide tasks       → Creating, completing, and flagging tasks\n'
    '  /guide drafts      → Submitting and reviewing content drafts\n'
    '  /guide connections → Tracking follow-ups and prospect connections\n'
    '  /guide setup       → Setting up and configuring a workspace\n'
    '  /guide invoicing   → Generating and tracking invoice periods\n'
    '  /guide reports     → All report types and when they are sent\n\n'
    'Tip: Type /menu at any time to take action with guided buttons.'
)

ROLE_HELP = {
    Role.VA: (
        'VA Quick Reference\n\n'
        'LOG HOURS (do this daily):\n'
        '  /hours today 4 LinkedIn outreach\n'
        '  /hours yesterday 6 Email campaigns\n'
        '  or /menu → Log hours\n'
        '  Check logged hours: /myweek\n\n'
        'SUBMIT YOUR TIMESHEET (end of week):\n'
        '  /submit hours   (or /menu → Submit timesheet)\n'
        '  Tip: Check /myweek first to confirm all hours are logged\n\n'
        'TASKS:\n'
        '  /tasks           → see your open tasks\n'
        '  /done [task_id]  → mark a task complete\n'
        '  /cantdo [task_id] skill [note]  → flag as blocked\n'
        '  or /menu → My tasks\n\n'
        'DRAFTS:\n'
        '  /draft linkedin Your post content here\n'
        '  or /menu → Submit draft\n'
        '  Check status: /drafts\n\n'
        'FOLLOW-UPS:\n'
        '  /connection "Name" LinkedIn  → log a new connection\n'
        '  /followups  → see who needs a follow-up\n'
        '  /followdone "Name" / /replied "Name" / /booked "Name"\n\n'
        'QUICK ACTIONS:\n'
        '  /menu → Quick actions → Ask / Flag / Confirm\n\n'
        'For detailed help: /guide hours  |  /guide timesheets  |  /guide tasks'
    ),
    Role.SUPERVISOR: (
        'Supervisor Quick Reference\n\n'
        'TIMESHEETS:\n'
        '  /timesheets          → see all pending timesheets\n'
        '  (Approve/query via private bot buttons)\n\n'
        'TEAM MANAGEMENT:\n'
        '  /groups              → see all users and their roles\n'
        '  /adduser [tg_id] VA [Name]  → add a VA\n'
        '  /set supervisor [va_id] [sup_id]  → assign supervisor\n'
        '  /set rate [va_id] [amount]        → set hourly rate\n'
        '  or /menu → Add user / Set supervisor / Set rate\n\n'
        'TASKS:\n'
        '  /tasks      → all open tasks\n'
        '  /overdue    → tasks open 48h+\n'
        '  /flagged    → tasks VAs can\'t complete\n'
        '  /assign [task_id] [va_id]  → assign to a VA\n\n'
        'DRAFTS:\n'
        '  /drafts  → review draft submissions\n'
        '  (Approve/revise via private bot buttons)\n\n'
        'REPORTS:\n'
        '  /weekly     → weekly operational summary\n'
        '  /monthly    → monthly overview\n'
        '  /report all → executive summary across all groups\n'
        '  /stats      → team activity summary\n\n'
        'INVOICING:\n'
        '  /invoice summary [va_tg_id] [YYYY-MM-DD:YYYY-MM-DD]\n'
        '  /invoice sent [va_tg_id] [YYYY-MM-DD:YYYY-MM-DD]\n\n'
        'For detailed help: /guide timesheets  |  /guide invoicing  |  /guide reports'
    ),
    Role.CLIENT: (
        'Client Quick Reference\n\n'
        'APPROVALS:\n'
        '  Timesheets and drafts are sent to you as private messages.\n'
        '  Use the Approve / Query buttons to respond.\n\n'
        'REPORTS:\n'
        '  /weekly   → what was done this week\n'
        '  /monthly  → monthly overview\n\n'
        'SATISFACTION CHECKS:\n'
        '  Your supervisor sends check-ins — just tap a rating button.\n'
        '  /scores   → see your satisfaction history\n\n'
        'INFO:\n'
        '  /profile  → your registered details\n'
        '  /links    → booking links for this workspace\n'
        '  /drafts   → view submitted content drafts\n\n'
        'AUTOMATED DIGESTS (sent to you automatically):\n'
        '  • Friday 5pm: Weekly digest with pending approvals\n'
        '  • Monthly report every first Monday\n\n'
        'For detailed help: /guide timesheets  |  /guide reports'
    ),
    Role.BUSINESS_MANAGER: (
        'Business Manager Quick Reference\n\n'
        'You have full access: all supervisor actions + client approvals.\n\n'
        'WORKSPACE:\n'
        '  /groups    → all users and roles\n'
        '  /auditlog  → recent changes to the workspace\n'
        '  /update [field] [value]  → update client settings\n\n'
        'TEAM:\n'
        '  /adduser [tg_id] [ROLE] [Name]\n'
        '  /set supervisor [va_id] [sup_id]\n'
        '  /set rate [va_id] [amount]\n'
        '  /set timezone [tg_id|client] [timezone]\n'
        '  or /menu for guided flows\n\n'
        'TIMESHEETS & INVOICING:\n'
        '  /timesheets  → pending timesheets\n'
        '  /invoice summary [va_tg_id] [start:end]\n'
        '  /invoice sent [va_tg_id] [start:end]\n\n'
        'REPORTS:\n'
        '  /weekly / /monthly / /report all / /stats\n'
        '  /report all includes financial summaries (BM only)\n\n'
        'TASKS & DRAFTS:\n'
        '  /tasks / /overdue / /flagged / /assign / /drafts\n\n'
        'For detailed help: /guide setup  |  /guide invoicing  |  /guide reports'
    ),
}

TOPIC_GUIDES = {
    'hours': (
        'How to Log Hours (VA)\n\n'
        'Log your work hours each day so your timesheet stays accurate.\n\n'
        'QUICK COMMAND:\n'
        '  /hours today 4 LinkedIn outreach and email replies\n'
        '  /hours yesterday 6 Campaign setup and client meeting\n'
        '  /hours 2024-01-15 2 Strategy planning call\n\n'
        'FORMAT: /hours [date] [hours] [note]\n'
        '  date  → today, yesterday, or YYYY-MM-DD\n'
        '  hours → number like 0.5, 1, 2, 4, 6, 8\n'
        '  note  → brief description of the work done\n\n'
        'GUIDED MENU (step by step):\n'
        '  1. Type /menu\n'
        '  2. Tap "Log hours"\n'
        '  3. Choose Today or Yesterday\n'
        '  4. Tap the number of hours\n'
        '  5. Send a short work description → Done!\n\n'
        'EDIT AN ENTRY:\n'
        '  /hours edit today 3 Revised note here\n'
        '  /hours edit 2024-01-15 4.5 Updated description\n\n'
        'Manager editing a VA\'s hours:\n'
        '  /hours edit [va_tg_id] [date] [hours] (note)\n\n'
        'CHECK YOUR WEEK:\n'
        '  /myweek → shows all logged entries for the current week\n\n'
        'TIPS:\n'
        '  • Log every working day — the bot reminds you at 12pm\n'
        '  • Minimum increment: 0.5h\n'
        '  • Log hours BEFORE submitting your timesheet'
    ),
    'timesheets': (
        'How Timesheets Work (Full Lifecycle)\n\n'
        'Timesheets collect your weekly hours and go through 3 approval stages:\n\n'
        '  VA submits → Supervisor reviews → Client approves → APPROVED ✅\n\n'
        '─────────────────────────────\n'
        'STEP 1 — VA Submits\n'
        '─────────────────────────────\n'
        '  1. Make sure all hours are logged: /myweek\n'
        '  2. Run: /submit hours  (or /menu → Submit timesheet)\n'
        '  3. The bot bundles the week\'s hours and sends to your supervisor\n\n'
        '─────────────────────────────\n'
        'STEP 2 — Supervisor Reviews\n'
        '─────────────────────────────\n'
        '  • Supervisor gets a private message with the hours breakdown\n'
        '  • They tap: "Approve and send to client" OR "Mark as queried"\n'
        '  • If queried: VA gets a note and must fix and resubmit\n'
        '  • Supervisors can also check: /timesheets\n\n'
        '─────────────────────────────\n'
        'STEP 3 — Client Final Approval\n'
        '─────────────────────────────\n'
        '  • Client gets a private message with the hours summary\n'
        '  • They tap: "Approve final" OR "I have a question"\n'
        '  • Once approved → status = APPROVED ✅\n\n'
        '─────────────────────────────\n'
        'AUTOMATIC REMINDERS\n'
        '─────────────────────────────\n'
        '  • VAs: Friday 4pm — reminder to submit timesheet\n'
        '  • Supervisors: Daily 2pm — action digest with pending items\n'
        '  • Clients: Friday 5pm — digest of pending approvals\n\n'
        '─────────────────────────────\n'
        'INVOICING (after approval)\n'
        '─────────────────────────────\n'
        '  /invoice summary [va_tg_id] [YYYY-MM-DD:YYYY-MM-DD]\n'
        '  /invoice sent [va_tg_id] [YYYY-MM-DD:YYYY-MM-DD]\n'
        '  → See /guide invoicing for full invoicing steps'
    ),
    'tasks': (
        'How to Manage Tasks\n\n'
        'Tasks are work items tracked for VAs and the team.\n\n'
        'CREATE A TASK:\n'
        '  /task Research top LinkedIn hashtags for Q2\n'
        '  or /menu → Create task → type description\n\n'
        'VIEW YOUR TASKS:\n'
        '  /tasks                → all open tasks\n'
        '  /menu → My tasks      → tap any task to act on it\n\n'
        'COMPLETE A TASK:\n'
        '  /done [task_id]\n'
        '  Example: /done 12\n'
        '  or /menu → My tasks → tap task → Mark Done\n\n'
        'FLAG A TASK (if blocked):\n'
        '  /cantdo [task_id] skill [optional note]\n'
        '  /cantdo [task_id] time [optional note]\n'
        '  Examples:\n'
        '    /cantdo 12 skill No Canva access\n'
        '    /cantdo 12 time Too many priorities this week\n'
        '  or /menu → My tasks → tap task → Can\'t Do\n\n'
        'SUPERVISOR ACTIONS:\n'
        '  /assign [task_id] [va_user_id]  → assign task to a VA\n'
        '  /overdue   → tasks open longer than 48 hours\n'
        '  /flagged   → tasks flagged as blocked\n'
        '  /menu → Pending tasks  → view and assign team tasks\n\n'
        'TASK STATUSES:\n'
        '  OPEN    → in progress\n'
        '  DONE    → completed ✅\n'
        '  FLAGGED → blocked, needs attention ⚠️\n\n'
        'TIPS:\n'
        '  • VA gets auto-notified when tasks are assigned\n'
        '  • Supervisors get a daily digest with open/flagged tasks\n'
        '  • Use /flag to alert your supervisor about any issue'
    ),
    'drafts': (
        'How Draft Submissions Work\n\n'
        'VAs submit content drafts for supervisor and client review before posting.\n\n'
        'SUBMIT A DRAFT:\n'
        '  /draft linkedin Your LinkedIn post content goes here...\n'
        '  /draft email Subject line and full email body here...\n'
        '  /draft instagram Caption for the Instagram post...\n'
        '  /draft other Any other content platform\n'
        '  or /menu → Submit draft → pick platform → send content\n\n'
        'PLATFORMS: linkedin, email, instagram, other\n\n'
        'CHECK YOUR DRAFTS:\n'
        '  /drafts → see all your recent draft submissions and statuses\n\n'
        'MARK AS POSTED (after approval):\n'
        '  /posted DFT-001  (use the draft code from /drafts)\n\n'
        '─────────────────────────────\n'
        'REVIEW FLOW\n'
        '─────────────────────────────\n'
        '1. VA submits draft → status: PENDING\n'
        '2. Supervisor gets private message + Approve/Revise buttons\n'
        '   • Approve: client gets it for final review\n'
        '   • Revise: VA gets a revision note\n'
        '3. Client gets private message + Approve/Revise buttons\n'
        '   • Approve: VA marks as posted with /posted [code]\n'
        '   • Revise: VA gets the note and can resubmit\n\n'
        'RESUBMITTING AFTER REVISION:\n'
        '  Just use /draft again with the updated content.\n'
        '  The system links it to the original automatically.\n\n'
        'DRAFT STATUSES:\n'
        '  PENDING  → waiting for supervisor review\n'
        '  APPROVED → ready to post\n'
        '  REVISED  → changes requested\n'
        '  POSTED   → published ✅'
    ),
    'connections': (
        'How to Track Follow-Ups & Connections\n\n'
        'Log every prospect connection — the bot tracks follow-ups automatically.\n\n'
        'LOG A NEW CONNECTION:\n'
        '  /connection "Sarah Jones" LinkedIn\n'
        '  /connection "Tom Wilson" Email\n'
        '  or /menu → Log connection → pick platform → send name\n\n'
        'PLATFORMS: LinkedIn, Email, Phone, Other\n\n'
        'VIEW PENDING FOLLOW-UPS:\n'
        '  /followups  → shows all connections due for follow-up\n\n'
        'UPDATE STATUS AFTER INTERACTION:\n'
        '  /followdone "Sarah Jones"  → followed up (auto-schedules next in 3 days)\n'
        '  /replied "Sarah Jones"     → prospect replied back\n'
        '  /booked "Sarah Jones"      → meeting or call booked 🎉\n'
        '  /noresponse "Sarah Jones"  → no response, closed\n\n'
        'HOW THE BOT MANAGES FOLLOW-UPS:\n'
        '  • Log connection → follow-up scheduled in 3 days\n'
        '  • /followdone   → follow-up rescheduled another 3 days\n'
        '  • /replied      → marks as replied (supervisor notified)\n'
        '  • /booked       → closes the follow-up loop\n'
        '  • /noresponse   → marks closed with no response\n\n'
        'AUTOMATIC REMINDERS:\n'
        '  • Daily 9am: VA gets nudge for due follow-ups\n'
        '  • Supervisor sees follow-up counts in daily digest at 2pm\n\n'
        'TIPS:\n'
        '  • Log connections the same day you make them\n'
        '  • /followups shows how many are overdue'
    ),
    'setup': (
        'How to Set Up a Workspace\n\n'
        'Run the setup command in the Telegram group you want to manage:\n\n'
        'SETUP COMMAND:\n'
        '  /setup | Client Name | Business Name | Timezone | Primary Service | Tagline | Description\n\n'
        'Example:\n'
        '  /setup | Jane Smith | BeeSmartVA | Europe/Paris | Lead Generation | Smart VA support | Daily VA operations for Jane\n\n'
        'After setup: you are automatically registered as Business Manager.\n\n'
        'TIMEZONE FORMAT:\n'
        '  Use IANA timezone names:\n'
        '  Europe/Paris, Asia/Manila, America/New_York, Asia/Dubai, UTC\n'
        '  Full list: en.wikipedia.org/wiki/List_of_tz_database_time_zones\n\n'
        '─────────────────────────────\n'
        'ADD TEAM MEMBERS\n'
        '─────────────────────────────\n'
        '  /adduser [telegram_id] VA [Full Name]\n'
        '  /adduser [telegram_id] SUPERVISOR [Full Name]\n'
        '  /adduser [telegram_id] CLIENT [Full Name]\n'
        '  /adduser [telegram_id] BUSINESS_MANAGER [Full Name]\n'
        '  or /menu → Add user (guided with buttons)\n\n'
        'How to get a Telegram user ID:\n'
        '  Ask them to message @userinfobot on Telegram — it shows their ID.\n\n'
        '─────────────────────────────\n'
        'CONFIGURE THE TEAM\n'
        '─────────────────────────────\n'
        '  /set supervisor [va_id] [supervisor_id]   → assign VA\'s supervisor\n'
        '  /set rate [va_id] [hourly_amount]          → set VA\'s hourly rate\n'
        '  /set timezone [tg_id|client] [timezone]   → update timezone\n'
        '  /update [field] [value]                   → update client settings\n\n'
        'MANAGE & AUDIT:\n'
        '  /groups    → see all registered users and their roles\n'
        '  /auditlog  → see all recent changes made to the workspace'
    ),
    'invoicing': (
        'How Invoicing Works\n\n'
        'Invoicing is based on APPROVED timesheets only.\n'
        'Only supervisors and business managers can run invoice commands.\n\n'
        '─────────────────────────────\n'
        'STEP 1 — View the invoice summary\n'
        '─────────────────────────────\n'
        '  /invoice summary [va_tg_id] [YYYY-MM-DD:YYYY-MM-DD]\n\n'
        '  Example:\n'
        '  /invoice summary 123456789 2024-01-01:2024-01-31\n\n'
        '  This shows:\n'
        '    • Total approved hours in the period\n'
        '    • Hourly rate applied\n'
        '    • Total amount owed\n\n'
        '─────────────────────────────\n'
        'STEP 2 — Mark invoice as sent\n'
        '─────────────────────────────\n'
        '  /invoice sent [va_tg_id] [YYYY-MM-DD:YYYY-MM-DD]\n\n'
        '  Example:\n'
        '  /invoice sent 123456789 2024-01-01:2024-01-31\n\n'
        '  This records the period as invoiced in the system.\n\n'
        'HOW TO FIND VA TELEGRAM ID:\n'
        '  /groups → shows all users with their IDs\n'
        '  The Telegram ID column is what you use here.\n\n'
        'NOTES:\n'
        '  • Only approved timesheets count — pending ones are excluded\n'
        '  • Rate used is what was set at time of approval\n'
        '  • Update rates with: /set rate [va_id] [amount]\n'
        '  • Each period can only be invoiced once'
    ),
    'reports': (
        'Reports & Analytics Guide\n\n'
        'Reports are role-based — each role sees what\'s relevant to them.\n\n'
        '─────────────────────────────\n'
        'FOR VAs\n'
        '─────────────────────────────\n'
        '  /myweek    → this week\'s logged hours\n'
        '  /tasks     → open tasks assigned to you\n'
        '  /drafts    → your draft submissions and statuses\n'
        '  /followups → connections due for follow-up\n\n'
        '─────────────────────────────\n'
        'FOR SUPERVISORS & BUSINESS MANAGERS\n'
        '─────────────────────────────\n'
        '  /weekly      → weekly summary (tasks, drafts, connections, hours)\n'
        '  /monthly     → monthly overview with team trends\n'
        '  /report all  → executive summary (BMs get financials too)\n'
        '  /stats       → team activity dashboard\n'
        '  /timesheets  → pending timesheets awaiting review\n'
        '  /flagged     → tasks blocked by VAs\n'
        '  /overdue     → tasks open 48h+\n\n'
        '─────────────────────────────\n'
        'FOR CLIENTS\n'
        '─────────────────────────────\n'
        '  /weekly   → summary of work done this week\n'
        '  /monthly  → monthly overview\n'
        '  /scores   → satisfaction score history\n\n'
        '─────────────────────────────\n'
        'AUTOMATIC REPORT SCHEDULE\n'
        '─────────────────────────────\n'
        '  • Daily 9am    → VA morning nudge (tasks + follow-ups)\n'
        '  • Daily 12pm   → VA hour logging reminder\n'
        '  • Daily 2pm    → Supervisor action digest (pending items)\n'
        '  • Friday 4pm   → VA timesheet submission reminder\n'
        '  • Friday 5pm   → Client weekly digest (work done + pending approvals)\n'
        '  • Monday 10am  → Weekly report to supervisors/BMs\n'
        '  • First Monday 11am → Monthly report to supervisors/BMs\n\n'
        'All times are in each user\'s configured timezone.'
    ),
}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        role = actor.role if actor else None
    if role is None:
        msg = (
            'Welcome to BeeSmartVA!\n\n'
            'This group has not been set up yet.\n\n'
            'To get started:\n'
            '  1. Run /setup with your workspace details\n'
            '  2. Type /guide setup for the full setup instructions\n\n'
            'Already a team member? Ask your Business Manager to add you with /adduser.'
        )
    else:
        msg = f'Welcome back! You are registered as {role.value}.\nUse /menu for guided actions or /help for your quick reference.'
    await update.message.reply_text(msg, reply_markup=role_main_keyboard(role))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        role = actor.role if actor else None
    if role is None:
        await update.message.reply_text(GENERAL_GUIDE, reply_markup=role_main_keyboard(None))
        return
    await update.message.reply_text(ROLE_HELP[role], reply_markup=role_main_keyboard(role))


async def guide_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /guide and /guide [topic] and /howto [topic]."""
    topic = (context.args[0].lower() if context.args else None)
    if topic and topic in TOPIC_GUIDES:
        await update.message.reply_text(TOPIC_GUIDES[topic])
        return
    if topic:
        topic_list = '  ' + '\n  '.join(f'/guide {t}' for t in TOPIC_GUIDES)
        await update.message.reply_text(
            f'Unknown guide topic: "{topic}"\n\nAvailable topics:\n{topic_list}'
        )
        return
    # No topic — show role guide
    await help_command(update, context)


async def howto_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alias for /guide [topic]."""
    await guide_command(update, context)


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        client = await get_client_by_chat_id(session, update.effective_chat.id)
        if not actor or not client:
            await update.message.reply_text(
                'This group has not been set up yet.\n'
                'Run /guide setup for instructions on getting started.'
            )
            return
        await update.message.reply_text(
            f'Name: {actor.display_name}\n'
            f'Role: {actor.role.value if actor.role else "Unregistered"}\n'
            f'Client: {client.name}\n'
            f'Timezone: {client.timezone}'
        )


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
