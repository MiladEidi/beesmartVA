# Changelog

All notable changes to BeeSmartVA are recorded here, newest first.

---

## 2026-05-01 — Voice system overhaul: bug fixes + 7 new intents + smarter NLP

### Bug fixed
- **`list_drafts` never matched** — the normalizer was converting "drafts" → "draft" before intent scoring, so "show my drafts" always fell through to `create_draft`. Removed the bad phonetic correction; `list_drafts` now uses `r'\bdraft[s]?\b'` as a safety net.

### normalizer.py — expanded
- **More phonetic corrections:** `weak`→`week`, `ower`→`hour`, `blob`→`log`, `tas`→`task`, `some bit`→`submit`, `a-sign`→`assign`, `raid`→`rate`, `shedule`→`schedule`, `wrote back`/`got back`→`replied`, `ghosted`/`no reply`/`didn't reply`/`haven't heard`→`no response`
- **Word numbers 13–90:** thirteen through nineteen, and all tens (twenty, thirty … ninety) — teens handled before tens to avoid partial-match collisions
- **Compound hour phrases:** already present; ordering now correct (phrases before single words)
- **Expanded fillers:** `please`, `i want to`, `i need to`, `i have to`, `i'd like to`
- **Punctuation strip:** now also removes `-`, `–`, `—`, `…`, `:` so Whisper punctuation doesn't bleed into extracted args

### entities.py — expanded
- **"next Monday"** → returns the upcoming occurrence of that weekday (future)
- **"this Monday"** → returns the nearest occurrence within the current week
- **"the day before yesterday" / "2 days ago"** → correct date
- **Platform extractor** now recognises: `twitter`/`tweet`, `x.com`/`x post`, `facebook`, `tiktok`, `mail` (in addition to existing linkedin / instagram / email / other)

### router.py — 7 new intents + 4 improved
**New intents (40 total, up from 33):**
| Intent | Example phrases | Handler |
|---|---|---|
| `my_rate` | "what's my rate", "my hourly rate" | `rate_command` |
| `list_users` | "show all users", "who's in the team", "groups" | `groups_command` |
| `show_schedule` | "show my schedule", "client schedule" | `schedule_command` |
| `show_links` | "show links", "booking links", "calendar link" | `links_command` |
| `show_contacts` | "contacts", "show client contacts" | `contacts_command` |
| `show_prefs` | "my preferences", "show settings", "prefs" | `prefs_command` |

**Improved intents:**
- `replied` — now also matches "responded", "wrote back", "got back"
- `booked` — now also matches "scheduled a meeting/call/appointment"
- `no_response` — now also matches "no reply", "ghosted", "haven't heard", "didn't reply"
- `list_drafts` — required pattern broadened to `draft[s]?` (see bug fix above)
- `_hours_args` — strips more leading words (`i`, `want`, `to`, `please`, `a`, `the`) so note extraction is cleaner for natural speech like "log three hours today for client meeting"
- New platforms (`twitter`, `facebook`, `tiktok`) added to `_draft_args` strip list

### handler.py — better feedback
- **Intent label in reply:** after transcribing, the bot now shows `🎙 Heard: "…"\n→ Logging hours…` so users know exactly what action will run
- **No-match message** is now categorised (Tasks / Hours / Follow-ups / Drafts / Reports & Info) with 15 concrete examples instead of 6
- No-match message uses Markdown for readability

**Files changed:** `app/voice/normalizer.py`, `app/voice/entities.py`, `app/voice/router.py`, `app/voice/handler.py`

---

## 2026-04-30 — Voice command support via faster-whisper + signal-scoring router

Users can now send voice messages to the bot and have them executed as commands — no typing required.

### Architecture (`app/voice/`)

A new `app/voice/` package handles the full speech-to-command pipeline:

| File | Role |
|------|------|
| `transcriber.py` | Downloads the OGG/OPUS file from Telegram, converts to 16 kHz mono WAV via `ffmpeg`, and transcribes with `faster-whisper` (runs locally, no external API) |
| `normalizer.py` | Cleans the raw transcript: phonetic corrections, word-number conversion, filler-word removal, punctuation stripping |
| `entities.py` | Extracts typed values from free-form speech: dates, hours, task IDs, user IDs, draft platforms |
| `router.py` | Signal-scoring intent matcher — maps cleaned text to an existing handler function and its `context.args` list |
| `handler.py` | Telegram `MessageHandler(filters.VOICE)` entry point registered in `main.py` |

### Normalizer — two preprocessing passes

**Phonetic corrections** run first to fix common Whisper mishearings before any matching:
- `luck / lock / lag / lug` → `log`
- `tax / tusk / tass` → `task`
- `dun / don / dawn` → `done`
- `ours / powers` → `hours`
- `conform` → `confirm`, `booked` → `book`, `reply` → `replied`, etc.

**Word-number normalisation** converts spelled-out quantities to digits so entity extractors find them reliably:
- `one / two / three … twelve` → `1 / 2 / 3 … 12`
- `half an hour` → `0.5 hours`, `an hour and a half` → `1.5 hours`, `an hour` → `1 hour`

### Router — signal-scoring (order-independent)

The first version used sequential regex phrase matching, which required words in a specific order and failed if Whisper substituted a single key word. The router was rewritten to use a scoring system:

- Each intent defines **required signals** (regex patterns — ALL must be present anywhere in the text) and **boost signals** (each match adds +1 to the score).
- Every intent is scored; the highest scorer wins.
- Word order is irrelevant. "1 hour today log for client calls" and "log 1 hour today for client calls" both score the same for `log_hours`.
- A single keyword (e.g. `hour`) is enough to satisfy a required signal even if surrounding words were misheard.

33 intents cover the full command surface: tasks, hours, check-ins, follow-ups, drafts, reports, scores, and meta commands.

### Handler fix — monkey-patching removed

The initial handler attempted to prefix every bot reply with the transcript by replacing `msg.reply_text` with a closure at runtime. `telegram.Message` in python-telegram-bot v22 uses `__slots__`, so assigning an instance attribute on it raised `AttributeError` **outside** the `try` block, meaning the actual command handler was never called and the user received no response. Fixed by sending a plain "🎙 Heard: …" message before executing the handler, then calling the handler normally.

### Usage

Send a voice message. The bot replies with what it heard, then executes the command:
```
🎙 Heard: "Log 3 hours today for client calls"
✅ Logged 3h for 2026-04-30.
```

If the intent is not recognised, the bot shows the transcript and example commands so the user can diagnose and retry.

### Setup (server)
```bash
sudo apt install ffmpeg
pip install faster-whisper
```

Optional `.env` variables: `WHISPER_MODEL` (default `base`), `WHISPER_DEVICE` (default `cpu`), `WHISPER_LANG` (default `en`).

**Files changed:** `app/voice/__init__.py`, `app/voice/transcriber.py`, `app/voice/normalizer.py`, `app/voice/entities.py`, `app/voice/router.py`, `app/voice/handler.py`, `app/main.py`, `requirements.txt`

---

## 2026-04-27 — Setup parser hardening, timezone tolerance, guided invoice flow

### Setup command parser fix (`admin.py`)
The `/setup` command previously used `partition(" ")` to skip the command token, which caused the first field to be silently truncated whenever pipes had no leading space (e.g. `/setup|Jane|...` or `/setup| Jane|...`). The parser now walks past the command token character-by-character (stopping at the first space, pipe, or newline), so any spacing convention works.

Error messages now report how many fields were received so the user knows exactly what went wrong.

### Timezone tolerance (`admin.py`)
Both `/setup` and `/set timezone` now strip all whitespace from the timezone field before validation, so `Europe / Paris` is silently normalised to `Europe/Paris` instead of failing. The rejection message now lists five common IANA examples so users can copy-paste rather than guess.

### Guided Invoice flow added to `/menu` (`ui.py`)
Invoicing previously required knowing the VA's Telegram ID and typing a `YYYY-MM-DD:YYYY-MM-DD` range by hand — impossible without referencing `/groups` and a calendar. The menu now has a `🧾 Invoice` button (visible to supervisors and managers) with a full guided flow:

1. **Pick VA** — buttons showing all registered VAs by name
2. **Pick period** — This Month, Last Month, or Custom Range (free-text step)
3. **Review summary** — shows approved hours, rate, and total amount
4. **Mark as Invoiced** — one-tap confirmation, stored in the system

Custom range input accepts multiple natural formats: `2024-01-01 to 2024-01-31`, `2024-01-01:2024-01-31`, `2024-01-01 - 2024-01-31`.

**Files changed:** `app/handlers/admin.py`, `app/handlers/ui.py`

---

## 2026-04-27 — UX simplification: buttons that work, commands that forgive

The bot already had guided menus — but several key buttons didn't actually do anything. They told users to type a command instead. This pass makes every button in `/menu` complete the action immediately.

### Broken buttons fixed
- **Submit Timesheet button** (`/menu → Submit Timesheet`) — previously showed "Type `/submit hours` in the chat." Now it **submits the timesheet on the spot**: checks for a supervisor, runs the submission, notifies the supervisor privately, and confirms to the VA in one tap.
- **Weekly report button** (`/menu → Reports → Weekly Summary`) — previously said "Type `/weekly` in the chat." Now **posts the report to the group immediately**.
- **Monthly report button** — same fix: generates and posts the monthly report on tap.
- **Satisfaction Scores button** — same fix: posts scores on tap.
- **Executive Report button** — same fix: generates and sends the summary to the manager's private chat on tap.

### Command aliases (no more guessing subcommands)
- `/submit` — now works on its own; `/submit hours` still works too.
- `/report` — now works on its own; `/report all` still works too.
- `/send` — now works on its own; `/send scorecheck` still works too.

### Simpler welcome messages
- **Unregistered user / wrong chat** message: trimmed to the essential steps, less wall-of-text.
- **Registered user `/start`** reply: shorter greeting, same menu buttons.

### New imports added to `ui.py`
`submit_hours`, `executive_summary`, `monthly_report`, `weekly_report`, `score_history`, `decrypt_hourly_rate`, `get_client_by_chat_id`, `week_start_for`, `render_scores`, `render_timesheet_table`, `timesheet_supervisor_keyboard`.

**Files changed:** `app/handlers/ui.py`, `app/handlers/common.py`, `app/main.py`

---

## 2026-04-21 — Rate setting moved to private chat (confidentiality)

VA hourly rates are now set exclusively in a private chat with the bot. Previously, running `/set rate` or using the Set Rate menu in a group chat exposed the VA's salary to every group member.

### Changes
- **`/set rate` in a group** → bot deletes the command message, sends the supervisor a private message with instructions, and replies in the group with a short redirect notice — no rate is ever visible in the group
- **`/set rate` in private chat** → works fully via a new `resolve_actor_private` resolver that identifies the supervisor's workspace by their Telegram ID instead of the group chat ID
- **`/menu → Set Rate` in a group** → redirected with a message explaining to use private chat
- **`/menu → Set Rate` in private chat** → full guided flow (VA picker → amount → confirmation) works privately
- **New helpers added:**
  - `get_manager_workspaces` (`app/services/users.py`) — returns all supervisor/manager memberships for a Telegram user ID
  - `resolve_actor_private` (`app/services/auth.py`) — resolves actor context in a private chat
- **Help text** updated throughout to note that rate setting must be done in private chat

**Files changed:** `app/services/auth.py`, `app/services/users.py`, `app/handlers/admin.py`, `app/handlers/ui.py`, `app/handlers/common.py`

---

## 2026-04-21 — Rename BUSINESS_MANAGER role to MANAGER

The `BUSINESS_MANAGER` role has been renamed to `MANAGER` across the entire codebase for clarity and brevity.

### Changes
- **Enum** (`app/enums.py`): `Role.BUSINESS_MANAGER = 'BUSINESS_MANAGER'` → `Role.MANAGER = 'MANAGER'`
- **All code references** updated across services, handlers, and tests: `Role.BUSINESS_MANAGER` → `Role.MANAGER`
- **User-facing text** updated: "Business Manager" / "BUSINESS_MANAGER" replaced with "Manager" / "MANAGER" in all bot messages, help text, and command usage strings
- **UI button** updated: inline role-picker button now shows "Manager — full access"
- **Callback data** updated: `ui:adduserrole:BUSINESS_MANAGER` → `ui:adduserrole:MANAGER`

> **Note:** The database column value changes from `'BUSINESS_MANAGER'` to `'MANAGER'`. Run the following migration on existing databases:
> ```sql
> UPDATE user SET role = 'MANAGER' WHERE role = 'BUSINESS_MANAGER';
> ```

**Files changed:** `app/enums.py`, `app/services/auth.py`, `app/services/permissions.py`, `app/services/users.py`, `app/services/drafts.py`, `app/services/reports.py`, `app/services/scheduler.py`, `app/utils/telegram.py`, `app/handlers/admin.py`, `app/handlers/callbacks.py`, `app/handlers/checkins.py`, `app/handlers/common.py`, `app/handlers/hours.py`, `app/handlers/reports.py`, `app/handlers/tasks.py`, `app/handlers/ui.py`, `tests/test_services.py`

---

## 2026-04-21 — Comprehensive UX polish pass

A systematic audit of all handler files identified and fixed rough edges across the entire bot UX.

### Crash-safety improvements
- **Scheduler** (`scheduler.py`): Added `_safe_send()` helper that wraps every `bot.send_message()` in a try/except with a `logger.warning`. Wrapped both `job_daily` and `job_management_summary` in outer try/except so a single failing job never kills the scheduler loop. Added timezone validation with `logger.warning` + `continue` for malformed client timezones.
- **Quick-action flows** (`ui.py`): Wrapped `send_message` calls in quickask, quickflag, and quickconfirm flows with try/except. If the supervisor hasn't started a private chat with the bot, the VA now receives a clear explanation instead of a silent failure.
- **Checkins** (`checkins.py`): Same try/except treatment for `/ask`, `/flag`, `/confirm`, and `/notify client` supervisor/client sends.

### Input validation
- **`/hours`** (`hours.py`): Added `try/except` around `Decimal(hours)` parse, `hours <= 0` guard, and `hours > 24` guard. Both VA and manager paths of `/hours edit` have the same guards.
- **Set-rate flow** (`ui.py`): Added `amount <= 0` guard after the `InvalidOperation` catch so rates of zero or negative are rejected immediately.

### Empty-state guards
- **Team task menu**: Shows "No VAs are registered yet." instead of an empty inline keyboard when no VAs exist.
- **Set-supervisor flow step 1**: Shows a clear message when no VAs exist yet.
- **Set-supervisor flow step 2**: Shows a clear message when no supervisors exist yet.
- **Set-rate flow**: Shows a clear message when no VAs exist yet.

### Help text and ID consistency
- All help text updated to use `[va_user_id]`/`[supervisor_user_id]` (display IDs from `/groups`) instead of `[va_tg_id]` (Telegram user IDs).
- VA welcome, "no supervisor" error, and "no rate" error messages all show the VA's display ID with a "(IDs from /groups)" note.
- Task menu: fixed raw DB id display — now shows VA display name instead of `VA #123`.

**Files changed:** `app/handlers/ui.py`, `app/handlers/hours.py`, `app/handlers/checkins.py`, `app/services/scheduler.py`, `app/handlers/common.py`, `app/handlers/tasks.py`

---

## 2026-04-21 — Non-informative user IDs (display_id) + rate visibility audit

### Random 4-digit display IDs replace sequential user numbers
Previously every user was shown their sequential database primary key (1, 2, 3 …), which revealed exactly how many users were in the system. A user added as the third person would always see `#3`.

**What changed:**
- Added a `display_id` field to the `User` model — a randomly generated 4-digit number (1000–9999), unique across all users
- New users are assigned a `display_id` at creation time; the actual sequential DB primary key is never exposed to end users
- On startup, any existing users without a `display_id` are automatically backfilled with random values (handled by `init_db()` via a safe `ALTER TABLE … ADD COLUMN` + `UPDATE` loop)
- All user-facing displays updated: `/groups` listing, user-added confirmation, VA welcome message (`/start`), setup checklist, and inline user-picker menus
- All user-typed commands updated to accept `display_id` as input: `/set supervisor`, `/set rate`, `/assign`, `/rate [va_id]`
- Internal DB relationships and auth flows are unchanged — they continue to use the actual primary key

**Files changed:** `app/models.py`, `app/db.py`, `app/services/users.py`, `app/handlers/admin.py`, `app/handlers/ui.py`, `app/handlers/common.py`, `app/handlers/tasks.py`, `app/handlers/hours.py`

### Rate visibility audit — confirmed and documented
Audited all paths where hourly rates could be exposed. The system was already correctly restricting access:

| Role | What they can see |
|------|------------------|
| VA | Their **own** rate only (via `/rate`) |
| Client | **Nothing** — blocked at command level and timesheet approvals pass `rate=None` to the formatter |
| Supervisor / BM | Any VA's rate via `/rate [va_id]` |

The enforcement is in three places:
- `hours.py` — VA branch returns early with own rate; `has_manager_access()` blocks the CLIENT role with an explicit message
- `callbacks.py` — when supervisor approves a timesheet, the client's copy is rendered with `rate=None` so the `💰 Rate:` and `💵 Estimated:` lines never appear
- `reports.py` — no rate data is included in weekly/monthly reports visible to all roles

**Fix:** The setup guide (`/guide setup`) contained the incorrect text "Rates are encrypted and never visible to the VA." Updated to accurately state that VAs can see their own rate but clients cannot see rates at all.

---

## 2026-04-19 — Fix "Actor not registered" error on inline button callbacks in private chat

### Fix timesheet/draft/score inline buttons failing in private chat
- `resolve_actor` identifies the client via `chat.id`, which only works in group chats. In a private chat (where supervisors and clients receive notifications), `chat.id` is the user's own Telegram ID, so no client was found and every button press showed "Actor not registered in this group."
- Added `resolve_actor_for_client(session, update, client_id)` in `auth.py` for callbacks that already know the client from the record being acted on
- `timesheet_callback`: loads the timesheet first (to get `client_id`), then resolves actor via `resolve_actor_for_client`
- `draft_callback`: same pattern — loads draft first, then resolves actor
- `score_callback`: `client_id` is already embedded in the callback data; switched directly to `resolve_actor_for_client`
- Also fixed the same post-commit expired-instance bug in `timesheet_callback` `sup_approve` path (same root cause as the `/submit hours` fix)

---

## 2026-04-19 — Fix /submit hours silent crash (no response to VA)

### Fix `submit_hours_command` silent crash after session commit
- `session.commit()` expires all ORM instances; accessing `user.display_name`, `user.supervisor.telegram_user_id`, `timesheet.week_start_date`, etc. after commit raised `MissingGreenlet` in the async session, crashing the handler with no reply to the VA
- Fixed by reading all required ORM attribute values into local variables **before** calling `session.commit()`

---

## 2026-04-19 — Fix /rate to use internal va_user_id instead of Telegram ID

### Fix `/rate` VA lookup for managers
- `/rate [id]` now looks up the VA by their internal user ID (`User.id`) instead of Telegram ID
- Previously the command was unusable because managers don't know VAs' Telegram numeric IDs
- Usage hint updated to `/rate [va_user_id]` throughout

---

## 2026-04-19 — VAs can see their own rate; full draft client-review flow
**Commits:** `3878e60`, `43befc7`

### VAs can now view their own hourly rate
- `/rate` with no arguments now shows a VA their own hourly rate
- If no rate is set, they see a clear message with the exact command for their manager to set it
- VAs still cannot query other VAs' rates — that remains manager-only

### Full two-step draft review flow (supervisor → client → post)
- Added `CLIENT_PENDING` draft status for drafts awaiting client sign-off
- After supervisor approves a draft, the client receives the full draft content in private chat with Approve / Request Revision buttons
- After client approves, VA receives a ready-to-post notification with the `/posted` command
- Client revision requests send VA a "client requested changes" message with resubmit instructions
- Graceful fallback if client hasn't started the bot privately yet (supervisor is informed)
- **Automatic reminders:**
  - 48h — supervisor reminded if PENDING draft is still unreviewed
  - 48h — client reminded if CLIENT_PENDING draft is still awaiting their approval
  - 72h — supervisor escalated if client still hasn't responded
- `/guide drafts` updated to show all statuses including `CLIENT_PENDING` and the reminder schedule

---

## 2026-04-19 — Global Business Manager + VA onboarding improvements
**Commit:** `88cb0d7`

### Business Manager is now global across all workspaces
- A single Telegram user is the Business Manager for **all** groups, not one per group
- Added `GlobalConfig` database table to store the global BM identity
- `resolve_actor` now overrides the per-group role to `BUSINESS_MANAGER` for the global BM automatically
- Only the current global BM can set up new workspaces (`/setup`)
- Only the current global BM can assign or transfer the BM role
- New `/setmanager [telegram_id] [Name]` command — transfers the BM role globally, demotes the old BM to Supervisor in every workspace they belong to
- `BotContextUser` now carries `telegram_user_id` for reliable identity checks

### VA onboarding — clearer guidance at every step
- **`/adduser` confirmation for VAs** now shows a full setup checklist with ✅/❌ status for supervisor and rate, plus the exact commands to run with the VA's internal ID pre-filled
- **`/hours` errors** split into three distinct messages: (1) command used in private DM — tells VA to go to the group, (2) not registered — tells them to ask their manager, (3) wrong role — states their actual role
- **`/submit hours` error** when no supervisor is assigned now shows the VA's own internal user ID and the exact `/set supervisor` command for the manager to copy
- **`/start` for VAs** now shows an account readiness panel: supervisor status, rate status, what is and is not yet available, and next-step instructions
- **New `/guide va_checklist`** topic — step-by-step checklist for managers covering every prerequisite before a VA can log hours and submit timesheets, and what unlocks at each stage
- **Hours guide** (`/guide hours`) updated with a prerequisites section at the top

---

## 2026-04-17 — Hide rates from clients/VAs, animations and visual improvements
**Commit:** `60d28e9`

- Hourly rates are now hidden from VAs and clients — only supervisors and business managers can view them
- Added UI animations and visual polish across bot responses
- Various formatting and display improvements throughout

---

## 2026-04-14 — Rewrite all help messages as comprehensive single-screen guides
**Commit:** `14bb49d`

- Completely rewrote all role-based help text (`/help`) for VA, Supervisor, Client, and Business Manager
- Each role now gets a single comprehensive reference screen covering every command they can use
- Added 8 topic guides accessible via `/guide [topic]`: hours, timesheets, tasks, drafts, connections, setup, invoicing, reports
- Every guide includes step-by-step instructions, examples, and tips
- `/howto` added as an alias for `/guide`

---

## 2026-04-14 — Server deployment scripts
**Commit:** `a09a433`

- Added `start.sh` — sets up virtualenv, installs dependencies, and launches the bot
- Added `run.sh` — minimal launch wrapper
- Added `beesmart.service` — systemd unit file for running the bot as a background service with auto-restart on crash and auto-start on server reboot

---

## 2026-04-14 — Make every UI element clickable and self-explanatory
**Commit:** `e6c109a`

- All menus now use inline buttons wherever possible so users can tap instead of type
- Every action confirmation includes a next-step hint
- Error messages include usage examples and guide links
- Menu flows use "Step X of Y" framing so users always know where they are

---

## 2026-04-13 — Comprehensive guides and self-guiding flows
**Commit:** `b836727`

- Added `TOPIC_GUIDES` covering 8 workflows with step-by-step instructions and command examples
- Expanded `ROLE_HELP` for all four roles with full command references
- Improved `/start` for new or unregistered users with clear next-step prompts
- Enhanced all menu flows in `ui.py` with inline examples and success confirmations
- Improved all admin command error messages with full usage examples and numbered next steps
- Enforced Business Manager uniqueness — raises an error if a second BM is added without an explicit transfer; demotes the old BM to Supervisor on authorized transfer
- Added test for BM uniqueness and transfer logic

---

## 2026-04-13 — Initial commit
**Commit:** `51d35a3`

- Core bot structure: Telegram bot + FastAPI API running concurrently
- Role system: VA, Supervisor, Client, Business Manager
- Hour logging and weekly timesheet submission and approval flow
- Task creation, assignment, completion, and flagging
- Content draft submission with supervisor and client review
- Prospect connection tracking and follow-up reminders
- Satisfaction score collection
- Invoice generation based on approved timesheets
- Encrypted hourly rates and credentials storage (Fernet)
- Audit log for all manager actions
- APScheduler for automated reminders and scheduled reports
- SQLAlchemy async with SQLite (dev) and PostgreSQL (prod) support
