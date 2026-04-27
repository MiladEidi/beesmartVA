from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.db import SessionLocal
from app.enums import Role
from app.services.auth import resolve_actor
from app.services.users import decrypt_credentials, get_client_by_chat_id, get_user_by_internal_id
from app.utils.dates import format_schedule
from app.utils.telegram import role_main_keyboard

GENERAL_GUIDE = (
    'Welcome to BeeSmartVA\n\n'
    'This bot manages VA team workflows: hour logging, timesheets, task tracking, '
    'draft approvals, follow-up reminders, invoicing, and reporting.\n\n'
    '━━━━━━━━━━━━━━━━━━━━━\n'
    'HOW TO GET STARTED\n'
    '━━━━━━━━━━━━━━━━━━━━━\n'
    'Step 1 — Run this in your Telegram group:\n'
    '  /setup | Client Name | Business Name | Timezone | Service | Tagline | Description\n\n'
    '  Example:\n'
    '  /setup | Jane Smith | BeeSmartVA | Europe/Paris | Lead Gen | Smart VA support | Daily ops\n\n'
    '  Timezone: IANA format — Europe/Paris, Asia/Manila, America/New_York, UTC\n\n'
    'Step 2 — Add your team:\n'
    '  /adduser [telegram_id] VA [Full Name]\n'
    '  /adduser [telegram_id] SUPERVISOR [Full Name]\n'
    '  /adduser [telegram_id] CLIENT [Full Name]\n\n'
    '  How to get a Telegram ID: ask them to message @userinfobot\n\n'
    'Step 3 — Configure team (use IDs shown in /groups):\n'
    '  /set supervisor [va_user_id] [supervisor_user_id]\n'
    '  /set rate [va_user_id] [hourly_amount]\n\n'
    'Step 4 — Everyone types /start in the group to register.\n\n'
    '━━━━━━━━━━━━━━━━━━━━━\n'
    'ROLES IN THE SYSTEM\n'
    '━━━━━━━━━━━━━━━━━━━━━\n'
    'VA               → logs hours, submits timesheets, handles tasks & drafts\n'
    'SUPERVISOR       → reviews timesheets, manages team, approves drafts\n'
    'CLIENT           → gives final approvals, reviews content, rates satisfaction\n'
    'MANAGER          → full access (supervisor + client + workspace admin)\n\n'
    '━━━━━━━━━━━━━━━━━━━━━\n'
    'NAVIGATION\n'
    '━━━━━━━━━━━━━━━━━━━━━\n'
    '/menu  → guided button flows for every action\n'
    '/help  → complete role-specific reference\n'
    '/guide → step-by-step guides for each feature'
)

ROLE_HELP = {
    Role.VA: (
        'VA Complete Guide\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '1. LOG HOURS  (do this every working day)\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '/hours today 4 LinkedIn outreach and emails\n'
        '/hours yesterday 6 Campaign setup and meetings\n'
        '/hours 2024-01-15 2 Strategy planning call\n\n'
        'Format: /hours [date] [hours] [note]\n'
        '  date  → today / yesterday / YYYY-MM-DD\n'
        '  hours → 0.5, 1, 2, 4, 6, 8 ...\n'
        '  note  → brief description of the work\n\n'
        'Via menu: /menu → Log Hours → pick date → pick hours → send note\n\n'
        'Edit: /hours edit today 3 Revised description\n'
        'Check week: /myweek\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '2. SUBMIT TIMESHEET  (end of each week)\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'Step 1 — Verify all hours: /myweek\n'
        'Step 2 — Submit: /submit hours  (or /menu → Submit timesheet)\n'
        'Step 3 — Bot sends to your supervisor for review\n'
        'Step 4 — Supervisor approves or queries\n'
        '         If queried: fix your hours and resubmit\n'
        'Step 5 — Client gives final approval → APPROVED ✅\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '3. TASKS\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '/tasks              → see all your open tasks\n'
        '/done [task_id]     → mark a task complete  (e.g. /done 12)\n'
        '/cantdo 12 skill No Canva access  → flag as blocked (skill issue)\n'
        '/cantdo 12 time Too many priorities  → flag as blocked (time issue)\n'
        'Via menu: /menu → My Tasks → tap task → Mark Done / Can\'t Do\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '4. DRAFTS  (content for approval before posting)\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '/draft linkedin Your LinkedIn post text here...\n'
        '/draft email Subject line | Full email body\n'
        '/draft instagram Caption for the post\n'
        '/draft other Any other platform or content\n\n'
        'Check status: /drafts\n'
        'After approval: /posted DFT-001  (code shown in /drafts)\n'
        'Via menu: /menu → Submit Draft → pick platform → send content\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '5. CONNECTIONS & FOLLOW-UPS\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '/connection "Sarah Jones" LinkedIn  → log a new connection\n'
        '/followups                          → see who needs a follow-up\n\n'
        'Update after interacting:\n'
        '  /followdone "Sarah Jones"  → followed up (next due in 3 days)\n'
        '  /replied "Sarah Jones"     → they replied back\n'
        '  /booked "Sarah Jones"      → meeting or call booked 🎉\n'
        '  /noresponse "Sarah Jones"  → no response, closed\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'AUTO-REMINDERS (your timezone)\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '  9am daily   → tasks + follow-up nudge\n'
        '  12pm daily  → hour logging reminder\n'
        '  Fri 4pm     → submit timesheet reminder'
    ),
    Role.SUPERVISOR: (
        'Supervisor Complete Guide\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '1. TIMESHEET APPROVAL FLOW\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'When a VA submits hours, you get a private message with the full breakdown.\n\n'
        'Tap: ✅ Approve — hours look correct, send to client\n'
        '     ❓ Query  — I have a question (VA gets notified to fix and resubmit)\n\n'
        'After your approval, the client receives the timesheet for final sign-off.\n'
        'View all pending: /timesheets\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '2. TEAM MANAGEMENT\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'Add users:\n'
        '  /adduser [telegram_id] VA [Full Name]\n'
        '  /adduser [telegram_id] SUPERVISOR [Full Name]\n'
        '  /adduser [telegram_id] CLIENT [Full Name]\n'
        '  Via menu: /menu → Add User (guided with buttons)\n\n'
        'How to get a Telegram ID: ask them to message @userinfobot\n\n'
        'Assign supervisor:  /set supervisor [va_user_id] [supervisor_user_id]  (IDs from /groups)\n'
        'Set hourly rate:    /set rate [va_user_id] [amount]  ← in private chat only\n'
        'Update timezone:    /set timezone [tg_id|client] [timezone]\n'
        'View all users:     /groups\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '3. TASKS\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '/tasks              → all open tasks across the team\n'
        '/overdue            → tasks open longer than 48 hours\n'
        '/flagged            → tasks VAs have flagged as blocked\n'
        '/assign [task_id] [va_user_id]  → assign a task to a specific VA\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '4. DRAFT REVIEW\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'When a VA submits a draft, you get a private message.\n\n'
        'Tap: ✅ Approve — looks good, send to client for final review\n'
        '     ✏️ Revise  — needs changes (VA gets a revision request)\n\n'
        'After client approval the VA marks it as posted.\n'
        'View pending queue: /drafts\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '5. INVOICING\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'Step 1 — Preview the invoice:\n'
        '  /invoice summary [va_tg_id] [YYYY-MM-DD:YYYY-MM-DD]\n'
        '  Example: /invoice summary 123456789 2024-01-01:2024-01-31\n'
        '  Shows: approved hours, hourly rate, total amount owed\n\n'
        'Step 2 — Mark as invoiced:\n'
        '  /invoice sent [va_tg_id] [YYYY-MM-DD:YYYY-MM-DD]\n\n'
        'Get VA Telegram IDs from: /groups\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '6. REPORTS\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '/weekly      → weekly summary (tasks, hours, drafts, connections)\n'
        '/monthly     → monthly overview with team trends\n'
        '/report all  → executive summary across all groups\n'
        '/stats       → team activity dashboard\n\n'
        'AUTO-REPORTS:\n'
        '  Daily 2pm → action digest (pending timesheets, tasks, drafts)\n'
        '  Mon 10am  → weekly report\n'
        '  1st Mon   → monthly report'
    ),
    Role.CLIENT: (
        'Client Complete Guide\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '1. APPROVING TIMESHEETS\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'Your VA logs hours every day. At end of week they submit a timesheet.\n'
        'Your supervisor reviews it first, then it comes to you.\n\n'
        'You receive a private bot message with the full hours breakdown.\n\n'
        'Tap: ✅ Approve — hours look correct, all good\n'
        '     ❓ I have a question — flags it for your supervisor to follow up\n\n'
        'No action needed unless you receive a message from the bot.\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '2. APPROVING CONTENT DRAFTS\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'Your VA creates content (LinkedIn posts, emails, etc.) for your approval.\n'
        'After your supervisor pre-approves, you get a private bot message.\n\n'
        'Tap: ✅ Approve — looks good, ready to post\n'
        '     ✏️ Request Revision — needs changes\n\n'
        'After your approval, your VA marks it as posted.\n'
        'View all drafts: /drafts\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '3. REPORTS  (available any time)\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '/weekly   → what was done this week (tasks, hours, drafts, connections)\n'
        '/monthly  → monthly overview with team trends\n'
        '/scores   → your satisfaction score history\n'
        '/drafts   → all submitted content drafts and their status\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '4. SATISFACTION SCORES\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'Your supervisor sends you a monthly check-in message.\n'
        'Just tap one of the rating buttons in that message:\n\n'
        '  1 😕 Poor  2 😐 Okay  3 🙂 Good  4 😊 Great  5 🌟 Excellent\n\n'
        'View full history: /scores\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '5. AUTOMATED REPORTS  (sent to you automatically)\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '  Friday 5pm  → weekly digest + pending approvals\n'
        '  1st Monday  → monthly summary report\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '6. OTHER\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '/profile  → your registered name, role, and timezone\n'
        '/links    → booking links stored for this workspace\n'
        '/menu     → all available actions as tap buttons'
    ),
    Role.MANAGER: (
        'Manager Complete Guide\n\n'
        'You have full access: all supervisor actions + client approvals.\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '1. WORKSPACE SETUP\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'Initial setup (run once in your group):\n'
        '  /setup | Client Name | Business Name | Timezone | Service | Tagline | Description\n\n'
        '  Example:\n'
        '  /setup | Jane Smith | BeeSmartVA | Europe/Paris | Lead Gen | Smart VA support | Daily ops\n\n'
        'Add team members:\n'
        '  /adduser [tg_id] VA [Full Name]\n'
        '  /adduser [tg_id] SUPERVISOR [Full Name]\n'
        '  /adduser [tg_id] CLIENT [Full Name]\n'
        '  Via menu: /menu → Add User (guided with buttons)\n\n'
        'Configure team:\n'
        '  /set supervisor [va_user_id] [supervisor_user_id]  → assign supervisor\n'
        '  /set rate [va_user_id] [amount]                   → set hourly rate\n'
        '  /set timezone [tg_id|client] [timezone]   → update timezone\n'
        '  /update [field] [value]                   → update workspace info\n\n'
        'View workspace: /groups\n'
        'Audit changes:  /auditlog\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '2. TIMESHEET FLOW\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'VA submits → you receive a private message with hours breakdown\n'
        'Tap: ✅ Approve — send to client for final sign-off\n'
        '     ❓ Query  — VA notified to fix and resubmit\n\n'
        'After you approve, client receives the final approval request.\n'
        'View all pending: /timesheets\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '3. INVOICING\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'Step 1 — Preview: /invoice summary [va_tg_id] [YYYY-MM-DD:YYYY-MM-DD]\n'
        '  Shows: approved hours, rate, total amount owed\n\n'
        'Step 2 — Record: /invoice sent [va_tg_id] [YYYY-MM-DD:YYYY-MM-DD]\n\n'
        'Get VA Telegram IDs from: /groups\n'
        'Only APPROVED timesheets count — pending are excluded\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '4. TASKS & DRAFTS\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '/tasks           → all open tasks across the team\n'
        '/overdue         → tasks open 48h+\n'
        '/flagged         → tasks blocked by VAs\n'
        '/assign [task_id] [va_user_id]  → assign to a VA\n'
        '/drafts          → review draft queue (approve/revise via buttons)\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '5. REPORTS\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '/weekly      → weekly operational summary\n'
        '/monthly     → monthly overview\n'
        '/report all  → executive + financial summary (BM only)\n'
        '/stats       → team activity dashboard\n'
        '/scores      → satisfaction score history\n\n'
        'AUTO-REPORTS:\n'
        '  Daily 2pm  → action digest (pending items)\n'
        '  Mon 10am   → weekly report\n'
        '  1st Mon    → monthly report + financial summary'
    ),
}

TOPIC_GUIDES = {
    'va_checklist': (
        'VA Account Setup Checklist\n\n'
        'Before a VA can use the bot fully, the Manager must complete\n'
        'these steps in the Telegram group.\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'STEP 1 — Add the VA\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '  /adduser [telegram_id] VA [Full Name]\n\n'
        '  How to get a Telegram ID: ask the VA to message @userinfobot\n\n'
        '  After running this, the bot shows the VA\'s user ID.\n'
        '  Note it down — you need it for the steps below.\n\n'
        '  Alternatively, run /groups to see all users and their IDs.\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'STEP 2 — Assign a supervisor  [REQUIRED for timesheets]\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '  /set supervisor [va_user_id] [supervisor_user_id]\n\n'
        '  Example: /set supervisor 2847 5193\n\n'
        '  Without this, the VA can log hours but CANNOT submit timesheets.\n'
        '  The supervisor receives private review messages when the VA submits.\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'STEP 3 — Set hourly rate  [REQUIRED for invoicing]\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '  /set rate [va_user_id] [amount]   ← run this in a private chat with the bot\n\n'
        '  Example: /set rate 2847 15.50\n\n'
        '  Rates must be set in private chat — they are never shown in the group.\n'
        '  Rates are encrypted. VAs can only see their own rate; clients cannot see rates at all.\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'STEP 4 — Ask the VA to run /start in the group\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '  The VA types /start in the team Telegram group (not in private chat).\n'
        '  The bot shows their readiness status and what they can do.\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'WHAT THE VA CAN DO AT EACH STAGE\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'After Step 1 only:\n'
        '  ✅ Log hours (/hours today 4 note)\n'
        '  ✅ Check week (/myweek)\n'
        '  ✅ Create tasks, submit drafts, log connections\n'
        '  ❌ Submit timesheet (blocked — needs supervisor)\n\n'
        'After Step 2:\n'
        '  ✅ Submit timesheets (/submit hours)\n'
        '  ❌ Invoices (blocked — needs hourly rate)\n\n'
        'After Step 3:\n'
        '  ✅ Full invoicing available to managers\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'IMPORTANT: All bot commands must be used INSIDE the group.\n'
        'Private messages to the bot will not work for VA actions.\n'
        '━━━━━━━━━━━━━━━━━━━━━\n\n'
        'Check current VA status: /groups\n'
        'Full setup guide: /guide setup'
    ),
    'hours': (
        'How to Log Hours (VA)\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'PREREQUISITES\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'Before you can log hours:\n'
        '  ✅ You must be registered as VA — ask your manager: /adduser\n'
        '  ✅ You must run this command INSIDE the team group (not private chat)\n\n'
        'Before you can SUBMIT a timesheet (next step after logging):\n'
        '  ✅ A supervisor must be assigned to your account\n'
        '  If not yet assigned, ask your manager: /set supervisor [your_id] [sup_id]\n\n'
        'Not sure if you are set up? Type /start in the group to check your status.\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'LOG HOURS\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
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
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'EDIT AN ENTRY\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '  /hours edit today 3 Revised note here\n'
        '  /hours edit 2024-01-15 4.5 Updated description\n\n'
        'Manager editing a VA\'s hours:\n'
        '  /hours edit [va_tg_id] [date] [hours] (note)\n\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        'CHECK YOUR WEEK\n'
        '━━━━━━━━━━━━━━━━━━━━━\n'
        '  /myweek → shows all logged entries for the current week\n\n'
        'TIPS:\n'
        '  • Log every working day — the bot reminds you at 12pm\n'
        '  • Minimum increment: 0.5h\n'
        '  • Log hours BEFORE submitting your timesheet\n\n'
        'Full VA checklist: /guide va_checklist'
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
        '  PENDING        → waiting for supervisor review\n'
        '  CLIENT_PENDING → supervisor approved, waiting for client sign-off\n'
        '  APPROVED       → client approved, ready to post\n'
        '  REVISED        → changes requested (by supervisor or client)\n'
        '  POSTED         → published ✅\n\n'
        'REMINDERS (automatic):\n'
        '  48h → supervisor reminded if PENDING draft not reviewed\n'
        '  48h → client reminded if CLIENT_PENDING draft not approved\n'
        '  72h → supervisor alerted if client still hasn\'t responded'
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
        'After setup: you are automatically registered as Manager.\n\n'
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
        '  /adduser [telegram_id] MANAGER [Full Name]\n'
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
        'Only supervisors and managers can run invoice commands.\n\n'
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

        # For VAs, load the full user record to check readiness
        va_user = None
        if actor and role == Role.VA and actor.role_user_id:
            va_user = await get_user_by_internal_id(session, client_id=actor.client_id, user_id=actor.role_user_id)

    if role is None:
        if actor is None:
            # Group not set up OR user not in a group (private DM)
            msg = (
                'Welcome to BeeSmartVA!\n\n'
                'Commands must be used inside your team\'s Telegram group — not here.\n\n'
                'To set up a group:\n'
                '  1. Add this bot to the group\n'
                '  2. Run /setup in the group\n'
                '  3. Add team members with /adduser'
            )
        else:
            # Group exists but user is not registered
            msg = (
                'Welcome to BeeSmartVA!\n\n'
                'You are not registered in this group yet.\n\n'
                'Ask your Manager to add you:\n'
                '  /adduser [your_telegram_id] VA [Your Name]\n\n'
                'Get your Telegram ID: message @userinfobot\n'
                'Then run /start here again.'
            )
        await update.message.reply_text(
            msg,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('⚙️ Setup Guide', callback_data='ui:guide:setup')],
            ]),
        )
        return

    name = actor.display_name if actor else ''

    if role == Role.VA and va_user is not None:
        supervisor_ok = va_user.supervisor_id is not None
        rate_ok = va_user.hourly_rate_encrypted is not None

        sup_line = '✅ Supervisor assigned' if supervisor_ok else '❌ No supervisor assigned yet'
        rate_line = '✅ Hourly rate set' if rate_ok else '❌ No hourly rate set yet'

        if supervisor_ok and rate_ok:
            readiness = 'Your account is fully set up. You can log hours and submit timesheets.'
            next_steps = '/hours today [h] [note]  → log today\'s hours\n/myweek → check this week\'s hours'
        else:
            readiness = 'Your account is not fully set up yet.'
            actions = []
            if not supervisor_ok:
                actions.append(f'• Supervisor: ask your manager to run /set supervisor {va_user.display_id or va_user.id} [sup_id]')
            if not rate_ok:
                actions.append(f'• Rate: ask your manager to run /set rate {va_user.display_id or va_user.id} [amount]')
            next_steps = '\n'.join(actions)
            next_steps += '\n\nYou CAN already log hours. You CANNOT submit timesheets until a supervisor is assigned.'

        await update.message.reply_text(
            f'Welcome, {name}!\n\n'
            f'Role: VA\n'
            f'User ID: {va_user.display_id or va_user.id}\n\n'
            '━━━━━━━━━━━━━━━━━━━━━\n'
            'Account readiness\n'
            '━━━━━━━━━━━━━━━━━━━━━\n'
            f'{sup_line}\n'
            f'{rate_line}\n\n'
            f'{readiness}\n\n'
            f'{next_steps}\n\n'
            'Full guide: /help',
            reply_markup=role_main_keyboard(role),
        )
    else:
        await update.message.reply_text(
            f'Hi {name}! You are registered as {role.value}.\n\n'
            'Use the buttons below, or tap Help & Guide for step-by-step instructions.',
            reply_markup=role_main_keyboard(role),
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with SessionLocal() as session:
        actor = await resolve_actor(session, update)
        role = actor.role if actor else None
    guide_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton('📖 Topic guides — Hours, Tasks, Drafts…', callback_data='ui:helpguide')],
        [InlineKeyboardButton('🏠 Back to menu', callback_data='ui:backtomenu')],
    ])
    if role is None:
        await update.message.reply_text(GENERAL_GUIDE, reply_markup=guide_kb)
        return
    await update.message.reply_text(ROLE_HELP[role], reply_markup=guide_kb)


async def guide_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /guide and /guide [topic] and /howto [topic]."""
    topic = (context.args[0].lower() if context.args else None)
    if topic and topic in TOPIC_GUIDES:
        await update.message.reply_text(
            TOPIC_GUIDES[topic],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('◀ All guide topics', callback_data='ui:helpguide')],
                [InlineKeyboardButton('Back to menu', callback_data='ui:backtomenu')],
            ]),
        )
        return
    if topic:
        rows = [[InlineKeyboardButton(f'📖 {t.capitalize()} guide', callback_data=f'ui:guide:{t}')] for t in TOPIC_GUIDES]
        rows.append([InlineKeyboardButton('Back to menu', callback_data='ui:backtomenu')])
        await update.message.reply_text(
            f'Unknown guide topic: "{topic}"\n\nAvailable topics — tap one:',
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return
    # No topic — show clickable topic list
    rows = [
        [InlineKeyboardButton('✅ VA Checklist — steps before a VA can work', callback_data='ui:guide:va_checklist')],
        [InlineKeyboardButton('⏱ Hours — log & edit daily work', callback_data='ui:guide:hours')],
        [InlineKeyboardButton('📋 Timesheets — submit & approval flow', callback_data='ui:guide:timesheets')],
        [InlineKeyboardButton('✅ Tasks — create, complete, flag', callback_data='ui:guide:tasks')],
        [InlineKeyboardButton('📝 Drafts — submit content for review', callback_data='ui:guide:drafts')],
        [InlineKeyboardButton('🔗 Follow-ups — track prospect connections', callback_data='ui:guide:connections')],
        [InlineKeyboardButton('⚙️ Setup — workspace configuration', callback_data='ui:guide:setup')],
        [InlineKeyboardButton('💰 Invoicing — generate & track invoices', callback_data='ui:guide:invoicing')],
        [InlineKeyboardButton('📊 Reports — all types & auto-schedule', callback_data='ui:guide:reports')],
        [InlineKeyboardButton('Back to menu', callback_data='ui:backtomenu')],
    ]
    await update.message.reply_text(
        'Help & Guide\n\nTap a topic for step-by-step instructions:',
        reply_markup=InlineKeyboardMarkup(rows),
    )


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
                'Tap the guide button below to get started.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('⚙️ Setup Guide', callback_data='ui:guide:setup')],
                ]),
            )
            return
        await update.message.reply_text(
            f'👤 Your Profile\n\n'
            f'Name:      {actor.display_name}\n'
            f'Role:      {actor.role.value if actor.role else "Unregistered"}\n'
            f'Client:    {client.name}\n'
            f'Timezone:  {client.timezone}',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('❓ Help & Guide', callback_data='ui:helpguide')],
                [InlineKeyboardButton('Back to menu', callback_data='ui:backtomenu')],
            ]),
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
        if not client or not actor or actor.role not in {Role.SUPERVISOR, Role.MANAGER}:
            await update.message.reply_text('Only supervisors or managers can view stored credentials.')
            return
        value = decrypt_credentials(client)
        await update.message.reply_text(value or 'No encrypted credentials stored.')
