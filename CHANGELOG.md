# Changelog

All notable changes to BeeSmartVA are recorded here, newest first.

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
